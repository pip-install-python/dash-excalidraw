#!/usr/bin/env python
"""Stress the upload path: sizes, caps, eviction, TTL, and the GIF question.

Run it rather than trust a number in a commit message:

    python scripts/stress_file_uploads.py

WHAT THIS COVERS AND WHAT IT CANNOT. Everything here is the SERVER half — the
store, its caps, its eviction, and the backend seam. The half that actually
hurt on this page is the BROWSER half: Excalidraw decoding a large GIF on the
main thread. That cannot be measured from Python, and the numbers for it were
taken in a real tab and are quoted in docs/file-uploads. Do not let a green
run here be read as "uploads are fine"; it means the storage is fine.
"""

from __future__ import annotations

import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import file_backends, file_store  # noqa: E402


def _mb(n: int) -> str:
    return f"{n / (1024 * 1024):.2f} MB"


def _blob(size: int) -> bytes:
    # Incompressible-ish, so nothing downstream can quietly shrink it.
    return bytes((i * 7 + 13) % 256 for i in range(size))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def test_sizes() -> None:
    section("per-file sizes against the cap")
    cap = file_store.MAX_ENTRY_BYTES
    print(f"  cap: {_mb(cap)} (EXCALIDRAW_FILE_MAX_ENTRY_BYTES)")
    for size in (1024, 64 * 1024, 1024 * 1024, cap - 1, cap + 1):
        file_store.clear()
        t0 = time.perf_counter()
        try:
            file_store.put("probe", "application/octet-stream", _blob(size))
            ms = (time.perf_counter() - t0) * 1000
            got = file_store.get("probe")
            ok = got is not None and len(got[1]) == size
            print(f"  {_mb(size):>10}  stored in {ms:6.1f} ms  readback={ok}")
        except file_store.FileTooLarge:
            print(f"  {_mb(size):>10}  REFUSED (over the per-file cap) — correct")


def test_total_cap_and_eviction() -> None:
    section("total cap and oldest-first eviction")
    file_store.clear()
    chunk = 512 * 1024
    n = (file_store.MAX_TOTAL_BYTES // chunk) + 3
    for i in range(n):
        file_store.put(f"k{i:03d}", "application/octet-stream", _blob(chunk))
    live = [k for k, _ in file_store.items()]
    print(f"  wrote {n} x {_mb(chunk)} = {_mb(n * chunk)} against a "
          f"{_mb(file_store.MAX_TOTAL_BYTES)} cap")
    print(f"  survivors: {len(live)}  first={live[0] if live else None}  "
          f"last={live[-1] if live else None}")
    # The point of oldest-first: the newest write is always readable, which is
    # what the round trip between lastFileAdded and replaceFiles depends on.
    assert live and live[-1] == f"k{n - 1:03d}", "newest entry was evicted"
    assert "k000" not in live, "oldest entry survived past the cap"
    print("  newest survived, oldest evicted — correct for the round trip")


def test_ttl() -> None:
    section("TTL")
    original = file_store.TTL_SECONDS
    file_store.TTL_SECONDS = 1
    try:
        file_store.clear()
        file_store.put("ttl", "text/plain", b"x")
        assert file_store.get("ttl") is not None
        time.sleep(1.2)
        expired = file_store.get("ttl") is None
        print(f"  entry gone after its TTL: {expired}")
        assert expired
    finally:
        file_store.TTL_SECONDS = original


def test_backend_seam() -> None:
    section("the backend seam")
    from lib.file_backends import FileBackend, register_backend

    calls = {"put": 0, "get": 0}

    class Recording(FileBackend):
        name = "recording"

        def put(self, key, mime_type, data):
            calls["put"] += 1
            return f"https://cdn.example/{key}"

        def get(self, key):
            calls["get"] += 1
            return None  # a CDN backend serves bytes itself

        def url_for(self, key):
            return f"https://cdn.example/{key}"

    register_backend("recording", Recording)
    os.environ["EXCALIDRAW_FILE_BACKEND"] = "recording"
    file_backends.reset_for_tests()
    try:
        url = file_backends.backend().put("abc", "image/gif", b"gif")
        print(f"  put() -> {url}")
        assert url.startswith("https://cdn.example/"), "the seam did not take"
        print(f"  backend name reported: {file_backends.backend().describe()['name']}")
        print("  a CDN backend returns a URL this app does not serve — by design")
    finally:
        os.environ.pop("EXCALIDRAW_FILE_BACKEND", None)
        file_backends.reset_for_tests()


def test_gif_is_not_rasterised_server_side() -> None:
    section("GIF bytes survive the server")
    try:
        from PIL import Image
    except ImportError:
        print("  (PIL not installed — skipped)")
        return
    frames = [Image.new("RGB", (64, 64), (i * 20 % 256, 40, 200)) for i in range(6)]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:],
                   duration=80, loop=0)
    data = buf.getvalue()
    file_store.clear()
    file_store.put("anim", "image/gif", data)
    mime, back = file_store.get("anim")
    # Graphic Control Extension blocks are a good proxy for frame count.
    gce = sum(1 for i in range(len(back) - 1) if back[i] == 0x21 and back[i + 1] == 0xF9)
    print(f"  in: {len(data)} bytes, 6 frames | out: {len(back)} bytes, "
          f"{gce} GCE blocks, mime={mime}")
    assert back == data, "the store altered the bytes"
    print("  byte-identical — the store never re-encodes. Rasterisation is a")
    print("  BROWSER behaviour, which is why the component intercepts the drop.")


def main() -> int:
    print("Stress: /file-uploads storage path")
    print(f"backend: {file_backends.backend().describe()}")
    test_sizes()
    test_total_cap_and_eviction()
    test_ttl()
    test_backend_seam()
    test_gif_is_not_rasterised_server_side()
    file_store.clear()
    print("\nAll storage-side checks passed.")
    print("The browser-side cost of a large GIF is NOT covered here — see")
    print("docs/file-uploads for those measurements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
