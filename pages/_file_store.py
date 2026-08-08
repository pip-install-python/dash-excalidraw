"""In-memory 'blob storage' shared by the file-uploads demo.

A real deployment swaps this for S3/GCS/on-disk + a DB for the URL map.
Kept in its own module so both `app.py` (which serves blobs via Flask)
and `pages/file_uploads.py` (which stores them) can import without
circular-import acrobatics.
"""

from __future__ import annotations

import threading
from typing import Dict, Tuple

# fileId -> (mime_type, raw_bytes)
FILE_STORE: Dict[str, Tuple[str, bytes]] = {}

# Guards concurrent access from Flask request handlers vs. Dash callbacks.
FILE_STORE_LOCK = threading.Lock()

# URL prefix that app.py serves from. Kept here so the demo page doesn't
# need to know the Flask routing detail.
FILE_URL_PREFIX = "/excalidraw-files"


def viewer_url(store_key: str) -> str:
    """URL for the HTML viewer wrapper (used by embeddable iframes)."""
    return f"{FILE_URL_PREFIX}/{store_key}/viewer"


def put(file_id: str, mime_type: str, data: bytes) -> str:
    """Store a blob and return the URL to serve it from."""
    with FILE_STORE_LOCK:
        FILE_STORE[file_id] = (mime_type, data)
    return f"{FILE_URL_PREFIX}/{file_id}"


def get(file_id: str) -> Tuple[str, bytes] | None:
    with FILE_STORE_LOCK:
        return FILE_STORE.get(file_id)


def clear() -> None:
    with FILE_STORE_LOCK:
        FILE_STORE.clear()


def items() -> list[Tuple[str, Tuple[str, bytes]]]:
    with FILE_STORE_LOCK:
        return list(FILE_STORE.items())