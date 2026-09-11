"""A daily ceiling on what this site's AI pages can spend.

WHY THIS EXISTS. /ai-agent, /benchmark and /trace-image call paid APIs, and
until now the only thing between a visitor and an unbounded bill was the
sign-in gate. That stops anonymous spending; it does nothing about a signed-in
visitor running /benchmark thirty times, or a model that decides a prompt
deserves its whole 128K budget. The Stop button is a manual brake for a human
who is watching. This is the automatic one.

THE FIGURE IS THE OWNER'S, and it is the single constant below. Nothing else
in this module decides how much money is acceptable to lose in a day.

HOW IT IS ENFORCED, stated precisely because the guarantee is not "you will
never exceed this":

  * Admission uses the TYPICAL cost estimate, not the ceiling estimate. A
    128K-budget run on the dearest model has a ceiling near $6.40, so
    admitting on the ceiling would refuse almost everything under a modest cap
    while the real spend came in far lower.
  * Settlement records the ACTUAL cost from the response's token counts.
  * Therefore the day's total can overshoot the ceiling by at most ONE run's
    difference between typical and actual — bounded, not zero. If you need a
    hard cap, set the constant to the number you can afford to exceed by one
    run.

WHY DISKCACHE AND NOT A MODULE GLOBAL. The production image runs
`gunicorn --workers 2`. A counter in this module would give each worker its
own budget, so the real ceiling would be N times the configured one and would
change if WEB_CONCURRENCY did — a safety limit that silently depends on how
many processes happen to be running is not a limit. The same store the scene
buffer uses is shared by every worker on the instance.

WHAT IT IS NOT. This is per-INSTANCE, not per-account: two instances have two
budgets. It is not a billing record — provider invoices are authoritative and
this only counts what this app knows it asked for. And it cannot see spending
by anything other than this app.

ONE KNOWN HOLE, WRITTEN DOWN RATHER THAN LEFT TO BE FOUND. Gemini has no entry
in MODEL_PRICING, so a Gemini call cannot be estimated or recorded. It is
still REFUSED once the ceiling is reached — the check runs without an estimate
— but it does not COUNT towards the ceiling, so a day of nothing but Gemini
can exceed the cap without ever tripping it. Pricing those two models closes
it; until then the gap is here in writing.
"""

from __future__ import annotations

import atexit
import os
import threading
from datetime import datetime, timezone

import diskcache

# ---------------------------------------------------------------------------
#  THE DIAL. This is the owner's, and it is the only one.
# ---------------------------------------------------------------------------
#
# US dollars per UTC day, across every AI page and every provider together.
# Set deliberately low until the lanes have run in production for a while:
# too low costs a refused run and a clear message, too high costs money.
DAILY_CEILING_USD = 10.00

# An override for operations, so the cap can be moved without a deploy. The
# constant above stays the source of truth in code and the documented default;
# this only lets ops raise or lower it in an emergency. An unparseable value is
# IGNORED rather than treated as zero or as infinity — a typo in an env var
# must not silently switch the brake off, and must not take the site's AI
# pages down either.
_CEILING_ENV = "AI_DAILY_CEILING_USD"

# Stored as integer micro-dollars. Floats accumulated by repeated addition
# drift, and a budget that drifts is a budget nobody trusts.
_MICRO = 1_000_000

CACHE_DIR = os.environ.get(
    "AI_SPEND_DIR", os.path.join(os.environ.get("TMPDIR", "/tmp"), "excalidraw-ai-spend")
)

# Yesterday's total is worth keeping long enough to be looked at, and no
# longer. Eight days covers a week's glance.
_KEY_TTL = 8 * 24 * 3600

_cache: diskcache.Cache | None = None
_lock = threading.Lock()


class CeilingReached(RuntimeError):
    """Raised instead of making a paid call. Carries a message for the page."""


def cache() -> diskcache.Cache:
    """The shared store, opened once per process and never at import.

    Opening a Cache creates a directory and an SQLite file; doing that while
    Dash registers pages would put disk I/O on the boot path of every
    deployment, including ones that never call a model.
    """
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = diskcache.Cache(CACHE_DIR)
                atexit.register(_cache.close)
    return _cache


def ceiling() -> float:
    """The active ceiling in dollars."""
    raw = os.environ.get(_CEILING_ENV)
    if raw is None or not raw.strip():
        return DAILY_CEILING_USD
    try:
        value = float(raw)
    except (TypeError, ValueError):
        # A typo must not disable the brake. Fall back to the constant.
        return DAILY_CEILING_USD
    if value < 0:
        return DAILY_CEILING_USD
    return value


def _day_key(when: datetime | None = None) -> str:
    # UTC, not local: two workers can sit in different timezones only by
    # misconfiguration, but a day that rolls over at a different moment in
    # each of them would make the ceiling ambiguous for an hour.
    now = when or datetime.now(timezone.utc)
    return f"spend:{now.strftime('%Y-%m-%d')}"


def spent_today() -> float:
    """Dollars this instance has recorded today."""
    micros = cache().get(_day_key(), default=0)
    return (micros or 0) / _MICRO


def remaining() -> float:
    return max(0.0, ceiling() - spent_today())


def record(cost_usd: float) -> float:
    """Add an actual cost to today's total. Returns the new total.

    Under diskcache's own transaction, which is an SQLite transaction and so
    holds across PROCESSES — two workers settling at the same moment cannot
    lose one of the two amounts to a read-modify-write race.
    """
    if not cost_usd or cost_usd <= 0:
        return spent_today()
    c = cache()
    key = _day_key()
    with c.transact():
        current = c.get(key, default=0) or 0
        total = current + int(round(cost_usd * _MICRO))
        c.set(key, total, expire=_KEY_TTL)
    return total / _MICRO


def check(estimated_usd: float = 0.0) -> None:
    """Raise `CeilingReached` if this run must not start.

    Called BEFORE the request, so a refusal costs nothing. The message is
    written for the person who sees it on the page rather than for a log: it
    says what the limit is, what has gone, and that it resets — a bare
    "limit reached" reads as a broken site.
    """
    cap = ceiling()
    spent = spent_today()
    if spent >= cap:
        raise CeilingReached(
            f"Daily AI budget reached — ${spent:.2f} of ${cap:.2f} spent today. "
            f"This resets at midnight UTC. The limit protects the site owner's "
            f"API bill; it is not a fault with your prompt."
        )
    if estimated_usd and spent + estimated_usd > cap:
        raise CeilingReached(
            f"This run is estimated at ${estimated_usd:.2f} and only "
            f"${cap - spent:.2f} of today's ${cap:.2f} budget is left. Lower the "
            f"max-token budget or the effort, or try again after midnight UTC."
        )


def summary() -> dict:
    """For a status line or a control board."""
    cap = ceiling()
    spent = spent_today()
    return {
        "ceiling": cap,
        "spent": spent,
        "remaining": max(0.0, cap - spent),
        "fraction": (spent / cap) if cap else 1.0,
        "overridden": os.environ.get(_CEILING_ENV) not in (None, ""),
    }
