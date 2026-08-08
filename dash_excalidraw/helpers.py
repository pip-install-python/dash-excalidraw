"""Helpers for working with Excalidraw serialized data on the Python side.

The component already gives you two serialized variants via setProps:

- ``serializedData`` — canonical Excalidraw envelope. May contain inline
  ``data:`` URIs under ``files[*].dataURL`` when the user has just
  dropped a new image.
- ``externalizedSerializedData`` — same envelope with every inline
  ``data:`` URI stripped to ``None``. External URLs survive.

These helpers let you complete the production flow:

- :func:`decode_data_url` cracks the base64 payload carried by a
  ``lastFileAdded`` event so you can forward the bytes to S3/GCS/disk.
- :func:`strip_inline_files` removes inline base64 from a serialized
  envelope you want to persist right now, even before uploads finish.
- :func:`restore_inline_files` reunites a stored envelope with the URLs
  you assigned at upload time.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from typing import Dict, Iterable, Mapping, Tuple

_DATA_URL_RE = re.compile(r"^data:([^;,]*)(;base64)?,(.*)$", re.DOTALL)


def decode_data_url(data_url: str) -> Tuple[str, bytes]:
    """Decode a ``data:`` URL into ``(mime_type, raw_bytes)``.

    Raises:
        ValueError: if ``data_url`` is not a well-formed data URL.
    """
    if not isinstance(data_url, str):
        raise ValueError("data_url must be a string")
    match = _DATA_URL_RE.match(data_url)
    if not match:
        raise ValueError("not a data URL")
    mime = match.group(1) or "application/octet-stream"
    is_base64 = bool(match.group(2))
    payload = match.group(3)
    if is_base64:
        return mime, base64.b64decode(payload)
    return mime, urllib.parse.unquote_to_bytes(payload)


def _iter_file_entries(parsed: dict) -> Iterable[Tuple[str, dict]]:
    files = parsed.get("files") or {}
    for fid, entry in files.items():
        if isinstance(entry, dict):
            yield fid, entry


def strip_inline_files(
    serialized_str: str,
) -> Tuple[str, Dict[str, Dict[str, str]]]:
    """Remove inline base64 from a serialized envelope.

    Returns a tuple of ``(serialized_without_base64, removed)`` where
    ``removed`` is ``{fileId: {dataURL, mimeType}}`` — feed this to your
    uploader. The returned serialized string is safe to persist; you can
    later reunite it with the URLs via :func:`restore_inline_files`.
    """
    parsed = json.loads(serialized_str)
    removed: Dict[str, Dict[str, str]] = {}
    files = parsed.get("files") or {}
    new_files: Dict[str, dict] = {}
    for fid, entry in files.items():
        if not isinstance(entry, dict):
            new_files[fid] = entry
            continue
        data_url = entry.get("dataURL")
        if isinstance(data_url, str) and data_url.startswith("data:"):
            removed[fid] = {
                "dataURL": data_url,
                "mimeType": entry.get("mimeType", ""),
            }
            new_files[fid] = {**entry, "dataURL": None}
        else:
            new_files[fid] = entry
    parsed["files"] = new_files
    return json.dumps(parsed), removed


def restore_inline_files(
    serialized_str: str,
    url_map: Mapping[str, str],
) -> str:
    """Rewrite ``files[*].dataURL`` with entries from ``url_map``.

    ``url_map`` is ``{fileId: dataURL}`` — the replacement can be either
    a fresh base64 ``data:`` URI (rehydrated from storage) or an external
    HTTP URL. Keys not present in the envelope are ignored; file entries
    not present in ``url_map`` are left untouched.
    """
    parsed = json.loads(serialized_str)
    files = parsed.get("files") or {}
    for fid, data_url in url_map.items():
        entry = files.get(fid)
        if isinstance(entry, dict):
            files[fid] = {**entry, "dataURL": data_url}
    parsed["files"] = files
    return json.dumps(parsed)


__all__ = [
    "decode_data_url",
    "strip_inline_files",
    "restore_inline_files",
]