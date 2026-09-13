#!/usr/bin/env python
"""Record which source tree the committed JS bundle was built from.

WHY A STAMP AND NOT A TIMESTAMP. `check_release` asked "was the bundle
committed no earlier than src/ts?" — a proxy for "is the bundle current". The
proxy fails in both directions and has now failed twice:

  * a TEST-ONLY commit under src/ts read as a stale bundle (d9d615a), fixed by
    excluding tests from the pathspec;
  * a COMMENT-ONLY change to a bundled source produces a byte-identical
    bundle, so git records no change to it, so its last-commit time never
    advances — and the check goes red permanently, with no rebuild able to
    clear it because there is nothing to commit.

The second one has no pathspec that fixes it: a comment is in a file webpack
really does read. So this stops guessing from clocks. The build writes the
hash of the sources it consumed, and the check compares that hash to the
sources as they stand. "Built from this tree" is the actual question, and a
hash answers it exactly.

It also always changes when a source changes, so a rebuild always produces
something to commit — which is what unsticks the permanent-red case.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "ts"
STAMP = ROOT / "dash_excalidraw" / "build_stamp.json"


def _is_source(path: Path) -> bool:
    """The files webpack actually bundles.

    Mirrors `_BUNDLE_SOURCES` in check_release: tests and mocks are excluded
    because they never reach the bundle, and including them is what made a
    test-only commit look like a stale build.
    """
    if not path.is_file() or path.suffix not in (".ts", ".tsx", ".js", ".jsx"):
        return False
    parts = path.parts
    if "__mocks__" in parts:
        return False
    return ".test." not in path.name


def source_hash() -> tuple[str, int]:
    """A hash over the bundled sources, and how many were seen.

    The count is returned so a caller can refuse to trust a hash taken over
    nothing — an empty sweep and a clean sweep otherwise look identical.
    """
    digest = hashlib.sha256()
    files = sorted(p for p in SRC.rglob("*") if _is_source(p))
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest(), len(files)


def main() -> int:
    if not SRC.is_dir():
        print(f"[build-stamp] {SRC} is missing; nothing to stamp")
        return 0
    value, count = source_hash()
    if count == 0:
        print("[build-stamp] REFUSING: no bundle sources found — a stamp over "
              "nothing would make check_release pass on nothing")
        return 1
    STAMP.write_text(
        json.dumps({"sources_sha256": value, "source_files": count}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    print(f"[build-stamp] {count} sources -> {value[:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
