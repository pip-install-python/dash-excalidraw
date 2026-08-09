"""The background-callback manager for long-running work.

WHY THIS EXISTS
---------------
The /ai-agent page calls a thinking model. Measured on Claude Opus 5, a
moderately complex prompt takes ~100 seconds even with the token budget and
effort bounded — and ran 473 seconds before they were. A plain Dash callback
occupies its worker for that entire time, so on the two-worker deployment in
render.yaml, two concurrent generations make the whole site unreachable:
every other page, /healthz included, queues behind them. The CD health probe
then fails and the deploy is marked unhealthy — a docs outage caused by two
people drawing pictures at once.

A background callback hands the work to a separate process and frees the
worker immediately. The page's `running=` list already drives the UI state,
so nothing about the user-facing behaviour changes except that the site stays
up while a generation runs.

CHOOSING A BACKEND
------------------
`CeleryManager` when a broker URL is configured — the right answer for a real
multi-instance deployment, because the queue lives outside any one process.
`DiskcacheManager` otherwise: no broker to run, correct for local development
and for a single-host deployment where all workers share a filesystem.

Both are optional. With neither available this returns None, and the page
falls back to a synchronous callback rather than failing to import — a docs
site that renders slowly is better than one that does not boot, and the
package itself never touches any of this.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile

logger = logging.getLogger(__name__)


def _say(msg: str) -> None:
    """Boot diagnostics via print, not logging.

    This module runs during run.py's import, BEFORE anything calls
    logging.basicConfig() — pages/markdown.py does that later, during Dash()
    construction. So logger.info() here goes to a root logger still at
    WARNING and vanishes. That is not a style detail: it made the one signal
    needed to diagnose a silent worker failure itself silent. Every other boot
    line in run.py prints for the same reason.
    """
    print(f"[boilerplate] background: {msg}", flush=True)

_MANAGER = None
_RESOLVED = False


def _broker_url() -> str | None:
    """Celery broker, if this deployment has one."""
    return (
        os.environ.get("CELERY_BROKER_URL")
        or os.environ.get("REDIS_URL")
        or None
    )


def _build():
    choice = os.environ.get("BACKGROUND_CALLBACKS", "").strip().lower()

    if choice in {"off", "0", "false"}:
        _say("OFF (BACKGROUND_CALLBACKS) — generation runs synchronously")
        return None

    # DEFAULT OFF ON macOS. A deliberate retreat, not an oversight.
    #
    # diskcache runs the job in a forked child, and on this app that child
    # dies on macOS WITHOUT raising. Dash's dispatcher then sees
    # `not job_running and output is UNDEFINED`, answers the browser 204, and
    # the page waits forever for a job that is already gone. Had the worker
    # merely raised, Dash would have surfaced a BackgroundCallbackError — so
    # the child is being killed, not faulting.
    #
    # The likely mechanism is macOS fork-safety: the fork happens from a
    # werkzeug REQUEST THREAD, and a forked child of a multithreaded process
    # carrying Objective-C runtime state aborts instead of faulting, which
    # matches "killed, not raised" exactly. Forking from the MAIN thread works
    # fine here — which is precisely why every isolated test passed while the
    # running server kept failing.
    #
    # That diagnosis is UNCONFIRMED. Shipping a default that has failed three
    # times on a real machine, on the strength of an unconfirmed theory, is
    # the wrong trade. Linux forks cleanly and is where this actually matters
    # (render.yaml runs two gunicorn workers), so background stays ON there
    # and off here, where a blocked worker costs one developer some patience
    # rather than a live site.
    #
    # BACKGROUND_CALLBACKS=on opts in on macOS, and sets the ObjC fork-safety
    # escape hatch below.
    if sys.platform == "darwin" and choice not in {"on", "1", "true"}:
        _say(
            "OFF on macOS by default — the forked worker dies here and the "
            "page hangs. Generation runs synchronously (it blocks a worker "
            "for its duration). BACKGROUND_CALLBACKS=on to try it anyway."
        )
        return None

    broker = _broker_url()
    if broker:
        try:
            from celery import Celery
            from dash import CeleryManager

            app = Celery(
                __name__,
                broker=broker,
                backend=os.environ.get("CELERY_RESULT_BACKEND") or broker,
            )
            _say("Celery (broker configured)")
            return CeleryManager(app)
        except ImportError:
            # Named explicitly rather than swallowed: a deployment that sets a
            # broker URL has *asked* for Celery, and silently dropping to
            # diskcache would look like it worked while behaving differently
            # under load.
            logger.warning(
                "background callbacks: CELERY_BROKER_URL/REDIS_URL is set but "
                "celery is not installed — falling back to diskcache. Install "
                "celery[redis] or unset the variable."
            )

    try:
        import multiprocess
        import diskcache
        from dash import DiskcacheManager

        # macOS (and Windows) default to the "spawn" start method, which makes
        # the child RE-IMPORT the parent's __main__ module. For `python run.py`
        # that means re-executing run.py — which fails outright, because Dash
        # resolves its assets path from `__main__.__file__` and a spawned
        # child's __main__ has no __file__. The worker dies before running a
        # line of the callback, the job disappears, and the browser's poll gets
        # a 204 and quietly stops. Nothing is logged, and the page just sits
        # there: the failure is completely silent from both ends.
        #
        # Linux forks by default, so this never appears in CI or on Render —
        # only on a developer's Mac, which is the worst place for it to hide.
        #
        # "fork" skips the re-import entirely. The documented caveat is that
        # forking a process with live threads is unsafe; here the fork happens
        # from the request handler before the callback touches anything
        # thread-owned, which is the same bargain every Dash + diskcache setup
        # on Linux already makes silently.
        if sys.platform == "darwin":
            # Standard workaround for the abort described above. Must be set
            # before the fork; harmless on other platforms.
            os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

        if multiprocess.get_start_method(allow_none=True) != "fork":
            try:
                multiprocess.set_start_method("fork", force=True)
                _say("start method set to fork")
            except (RuntimeError, ValueError) as exc:
                _say(
                    f"COULD NOT select the fork start method ({exc}). On a "
                    "spawn platform the worker re-imports __main__ and dies; "
                    "set BACKGROUND_CALLBACKS=off to run synchronously."
                )
    except ImportError:
        logger.warning(
            "background callbacks: OFF — diskcache is not installed, so "
            "/ai-agent runs its model call synchronously and will block a "
            "worker for the duration. Install diskcache, multiprocess and "
            "psutil to enable."
        )
        return None

    # Under the app directory when writable, else the system temp dir: the
    # container filesystem is ephemeral either way, and these entries are
    # transient job state that must not survive a restart.
    root = os.environ.get("BACKGROUND_CACHE_DIR") or os.path.join(
        tempfile.gettempdir(), "excalidraw-background-cache"
    )
    _say(f"diskcache at {root}")
    return DiskcacheManager(diskcache.Cache(root))


def manager():
    """The callback manager, or None. Built once; safe to call repeatedly."""
    global _MANAGER, _RESOLVED
    if not _RESOLVED:
        _MANAGER = _build()
        _RESOLVED = True
    return _MANAGER


def enabled() -> bool:
    """Whether a page may pass ``background=True``.

    Pages call this at import time to decide, so it must be resolved before
    ``Dash()`` constructs — ``run.py`` imports this module first for exactly
    that reason.
    """
    return manager() is not None
