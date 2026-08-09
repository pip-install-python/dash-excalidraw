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
import tempfile

logger = logging.getLogger(__name__)

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
            logger.info("background callbacks: Celery (broker configured)")
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
        import diskcache
        from dash import DiskcacheManager
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
    logger.info("background callbacks: diskcache at %s", root)
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
