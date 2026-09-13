"""Where uploaded bytes actually live, and how to point that somewhere else.

`lib/file_store` has always said a real deployment "swaps this for S3/GCS/
on-disk plus a DB for the URL map". It said it in a docstring and offered no
seam to do it through: the store was a module-level dict with module-level
functions, so swapping it meant editing it.

This is the seam. A backend is three methods:

    put(key, mime_type, data) -> url     store bytes, return where to fetch them
    get(key)                  -> (mime_type, bytes) | None
    url_for(key)              -> url     where put() said they would be

That is the whole contract, and it is deliberately the smallest one that
works. Everything above it — the canvas, `replaceFiles`, the embeddable's
iframe, the drawer preview — only ever needs a URL back and the bytes at that
URL. Nothing above it knows whether the bytes are in this process, on a disk,
in Postgres, or behind Cloudflare R2.

CHOOSING ONE. `EXCALIDRAW_FILE_BACKEND` selects it:

    memory   (default)  the bounded in-process store — see lib/file_store
    disk                a directory, EXCALIDRAW_FILE_DIR

Anything else raises at import rather than falling back, because a storage
backend that silently is not the one you asked for is worse than a boot
failure: the site comes up, uploads appear to work, and the bytes are not
where you think.

WRITING YOUR OWN, which is the point of this file. Subclass `FileBackend`,
implement the three methods, and register it:

    class R2Backend(FileBackend):
        def __init__(self, bucket, public_base):
            self._bucket, self._base = bucket, public_base

        def put(self, key, mime_type, data):
            self._bucket.put_object(Key=key, Body=data, ContentType=mime_type)
            return self.url_for(key)          # e.g. https://cdn.example/<key>

        def get(self, key):
            # Only needed if THIS app serves the bytes. With a public CDN URL
            # the browser fetches them directly and this can return None.
            return None

        def url_for(self, key):
            return f"{self._base.rstrip('/')}/{key}"

    register_backend("r2", lambda: R2Backend(bucket, "https://cdn.example"))

Two things that change once the URL is not this app's own origin, and both
are the deployment's business rather than the component's:

  * CORS. Excalidraw fetches image bytes from the canvas, so the bucket must
    allow the site's origin. A CDN that serves images to <img> but refuses
    cross-origin fetches will render some things and not others.
  * Lifetime. The caps and the TTL in `lib/file_store` exist because that
    backend holds bytes in a web process on a 512 MB container. A bucket has
    none of those problems, and `DiskBackend`/your own should not inherit
    limits that were sized for somebody else's constraint.
"""

from __future__ import annotations

import os
import threading
from typing import Callable, Dict, Optional, Tuple


class FileBackend:
    """The three methods everything above storage depends on."""

    #: Human name, for the boot line and the /file-uploads panel.
    name = "unnamed"

    def put(self, key: str, mime_type: str, data: bytes) -> str:
        raise NotImplementedError

    def get(self, key: str) -> Optional[Tuple[str, bytes]]:
        raise NotImplementedError

    def url_for(self, key: str) -> str:
        raise NotImplementedError

    def describe(self) -> dict:
        """What the UI shows about this backend. Override to add detail."""
        return {"name": self.name, "serves_bytes": True}


class MemoryBackend(FileBackend):
    """The bounded in-process store. Delegates to :mod:`lib.file_store`.

    Kept as the default because it needs no configuration and no network, and
    because the demo it backs is a demo. Its caps are not timidity — it is an
    anonymous write surface in a web process, and the reasons are written out
    in that module.
    """

    name = "memory"

    def put(self, key: str, mime_type: str, data: bytes) -> str:
        from lib import file_store

        return file_store.put(key, mime_type, data)

    def get(self, key: str) -> Optional[Tuple[str, bytes]]:
        from lib import file_store

        return file_store.get(key)

    def url_for(self, key: str) -> str:
        from lib import file_store

        return f"{file_store.FILE_URL_PREFIX}/{key}"

    def describe(self) -> dict:
        from lib import file_store

        return {
            "name": self.name,
            "serves_bytes": True,
            "max_entry_bytes": file_store.MAX_ENTRY_BYTES,
            "max_total_bytes": file_store.MAX_TOTAL_BYTES,
            "ttl_seconds": file_store.TTL_SECONDS,
            "survives_restart": False,
            "shared_between_workers": False,
        }


class DiskBackend(FileBackend):
    """A directory. The smallest step up that survives a restart.

    Worth having as more than an example: it is the one backend that fixes
    the memory store's two real faults — bytes vanishing on redeploy, and two
    gunicorn workers holding different files — without any external service.
    It still serves through this app, so CORS stays a non-issue.
    """

    name = "disk"

    def __init__(self, root: str) -> None:
        self._root = root
        os.makedirs(self._root, exist_ok=True)

    def _path(self, key: str) -> str:
        # Keys are generated by this app (`ext-<hex><ext>`, or a content
        # hash), never by a visitor — but a traversal here would be a file
        # write outside the root, so it is refused rather than trusted.
        if os.path.sep in key or key in ("", ".", "..") or key.startswith("."):
            raise ValueError(f"unsafe storage key: {key!r}")
        return os.path.join(self._root, key)

    def put(self, key: str, mime_type: str, data: bytes) -> str:
        path = self._path(key)
        with open(path, "wb") as fh:
            fh.write(data)
        # The mime type travels beside the blob; guessing it back from the
        # extension loses application/json vs text/plain and similar pairs.
        with open(path + ".mime", "w", encoding="utf-8") as fh:
            fh.write(mime_type)
        return self.url_for(key)

    def get(self, key: str) -> Optional[Tuple[str, bytes]]:
        try:
            path = self._path(key)
            with open(path, "rb") as fh:
                data = fh.read()
            try:
                with open(path + ".mime", encoding="utf-8") as fh:
                    mime = fh.read().strip()
            except OSError:
                mime = "application/octet-stream"
            return mime, data
        except (OSError, ValueError):
            return None

    def url_for(self, key: str) -> str:
        from lib import file_store

        return f"{file_store.FILE_URL_PREFIX}/{key}"

    def describe(self) -> dict:
        return {
            "name": self.name,
            "serves_bytes": True,
            "root": self._root,
            "survives_restart": True,
            "shared_between_workers": True,
        }


_FACTORIES: Dict[str, Callable[[], FileBackend]] = {
    "memory": MemoryBackend,
    "disk": lambda: DiskBackend(
        os.environ.get("EXCALIDRAW_FILE_DIR", "/tmp/excalidraw-uploads")
    ),
}

_backend: Optional[FileBackend] = None
_lock = threading.Lock()


def register_backend(name: str, factory: Callable[[], FileBackend]) -> None:
    """Add a backend under a name `EXCALIDRAW_FILE_BACKEND` can select.

    Call it before the first `backend()` — at import of your app module is the
    natural place.
    """
    _FACTORIES[name] = factory


def backend() -> FileBackend:
    """The configured backend, built once.

    Not at import: constructing one may open a directory or a client, and a
    module import is the wrong place for either.
    """
    global _backend
    if _backend is None:
        with _lock:
            if _backend is None:
                choice = os.environ.get("EXCALIDRAW_FILE_BACKEND", "memory")
                factory = _FACTORIES.get(choice)
                if factory is None:
                    raise RuntimeError(
                        f"EXCALIDRAW_FILE_BACKEND={choice!r} is not registered. "
                        f"Known: {sorted(_FACTORIES)}. Refusing to fall back — "
                        f"a store that is silently not the one you configured "
                        f"is worse than a boot failure."
                    )
                _backend = factory()
    return _backend


def reset_for_tests() -> None:
    """Drop the built backend so a test can select another."""
    global _backend
    with _lock:
        _backend = None
