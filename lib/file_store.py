"""Bounded in-memory blob store backing the /file-uploads demo.

A real deployment swaps this for S3/GCS/on-disk plus a DB for the URL map.
The Dash-side contract is identical either way: an upload returns a URL, and
that URL is fed back to the canvas via the `replaceFiles` command.

WHY THE CAPS EXIST
------------------
This is an **anonymous write surface**. Any visitor can paste or drop an image
onto the canvas and the bytes land in this process. On localhost that was fine
for a year; on a public host an unbounded dict fed by anonymous uploads is a
memory-growth vector that ends in the container being OOM-killed, and on
Render's free tier that is the whole site going down.

So every entry is bounded three ways, and all three are required — any one
alone is bypassable:

  * per-entry cap   — one caller cannot post a 2 GB blob;
  * total cap       — many callers cannot post 10 000 small ones;
  * TTL             — a store that only ever grows still fills up eventually,
                      even under the two size caps.

Eviction is oldest-first, which is right for a demo: the bytes only need to
outlive the round-trip between `lastFileAdded` firing and `replaceFiles`
installing the returned URL. A visitor whose blob is evicted mid-session sees
the image fall back to Excalidraw's own inline copy, not an error.

Limits are env-tunable so a deployment with more headroom can raise them
without a code change. The defaults are sized for a 512 MB free-tier
container.
"""

from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple


def _env_int(name: str, default: int) -> int:
    """Read a positive int from the environment, falling back on nonsense.

    A malformed limit must not take the site down at import time, but it must
    also not silently disable the cap — so we fall back to the default and say
    so, rather than passing the bad value through.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        print(f"[file_store] {name}={raw!r} is not an integer; using {default}")
        return default
    if value <= 0:
        print(f"[file_store] {name}={value} must be positive; using {default}")
        return default
    return value


# One pasted image. 5 MB comfortably covers a screenshot; a photo straight off
# a phone is rejected, which is the correct answer for a drawing demo.
MAX_ENTRY_BYTES = _env_int("EXCALIDRAW_FILE_MAX_ENTRY_BYTES", 5 * 1024 * 1024)

# Everything currently held. Sized so the store cannot dominate a 512 MB
# container even when full.
MAX_TOTAL_BYTES = _env_int("EXCALIDRAW_FILE_MAX_TOTAL_BYTES", 64 * 1024 * 1024)

# How long a blob survives. Long enough for a browsing session, short enough
# that an idle host drains back to empty.
TTL_SECONDS = _env_int("EXCALIDRAW_FILE_TTL_SECONDS", 60 * 60)

# URL prefix the site serves blobs from. Kept here so the demo page never has
# to know the routing detail.
FILE_URL_PREFIX = "/excalidraw-files"


class _Entry:
    __slots__ = ("mime_type", "data", "stored_at")

    def __init__(self, mime_type: str, data: bytes) -> None:
        self.mime_type = mime_type
        self.data = data
        self.stored_at = time.monotonic()


class FileTooLarge(ValueError):
    """Raised when a single upload exceeds ``MAX_ENTRY_BYTES``.

    Explicit rather than a silent drop: the caller is a Dash callback that
    would otherwise hand the canvas a URL for bytes that were never stored,
    and the image would 404 later with nothing pointing at the cause.
    """


# Ordered so eviction is oldest-first without a separate index.
_STORE: "OrderedDict[str, _Entry]" = OrderedDict()
_LOCK = threading.Lock()
_total_bytes = 0


def _drop_locked(file_id: str) -> None:
    """Remove one entry and keep the byte tally honest. Caller holds the lock."""
    global _total_bytes
    entry = _STORE.pop(file_id, None)
    if entry is not None:
        _total_bytes -= len(entry.data)


def _expire_locked(now: Optional[float] = None) -> int:
    """Drop everything past its TTL. Returns how many went. Caller holds lock."""
    now = time.monotonic() if now is None else now
    dead = [k for k, e in _STORE.items() if now - e.stored_at > TTL_SECONDS]
    for k in dead:
        _drop_locked(k)
    return len(dead)


def viewer_url(store_key: str) -> str:
    """URL for the HTML viewer wrapper (used by ``embeddable`` iframes)."""
    return f"{FILE_URL_PREFIX}/{store_key}/viewer"


def put(file_id: str, mime_type: str, data: bytes) -> str:
    """Store a blob and return the URL to serve it from.

    Raises ``FileTooLarge`` if the single blob exceeds ``MAX_ENTRY_BYTES``.
    Evicts expired entries first, then the oldest, until the new blob fits
    under ``MAX_TOTAL_BYTES``.
    """
    global _total_bytes
    size = len(data)
    if size > MAX_ENTRY_BYTES:
        raise FileTooLarge(
            f"{file_id}: {size} bytes exceeds the {MAX_ENTRY_BYTES}-byte "
            "per-file limit (EXCALIDRAW_FILE_MAX_ENTRY_BYTES)"
        )

    with _LOCK:
        _expire_locked()
        # Replacing an existing id must not double-count its bytes.
        _drop_locked(file_id)
        while _STORE and _total_bytes + size > MAX_TOTAL_BYTES:
            _drop_locked(next(iter(_STORE)))
        _STORE[file_id] = _Entry(mime_type, data)
        _total_bytes += size

    return f"{FILE_URL_PREFIX}/{file_id}"


def get(file_id: str) -> Optional[Tuple[str, bytes]]:
    """Return ``(mime_type, data)``, or ``None`` if absent or expired."""
    with _LOCK:
        entry = _STORE.get(file_id)
        if entry is None:
            return None
        if time.monotonic() - entry.stored_at > TTL_SECONDS:
            _drop_locked(file_id)
            return None
        return entry.mime_type, entry.data


def clear() -> None:
    global _total_bytes
    with _LOCK:
        _STORE.clear()
        _total_bytes = 0


def items() -> List[Tuple[str, Tuple[str, bytes]]]:
    """Live (non-expired) entries, oldest first."""
    with _LOCK:
        _expire_locked()
        return [(k, (e.mime_type, e.data)) for k, e in _STORE.items()]


def stats() -> Dict[str, int]:
    """Observability for /healthz and the test suite."""
    with _LOCK:
        _expire_locked()
        return {
            "entries": len(_STORE),
            "total_bytes": _total_bytes,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "max_entry_bytes": MAX_ENTRY_BYTES,
            "ttl_seconds": TTL_SECONDS,
        }
