#!/usr/bin/env python
"""Pre-release consistency check for dash-excalidraw.

Run it before cutting a tag, and let CI run it on every pull request. It
catches the release-shaped mistakes that no functional test can see, because
the app and the component both work perfectly with all of them:

1. **Version drift across three files.** ``pyproject.toml`` decides what PyPI
   serves, but ``dash_excalidraw.__version__`` is read at import time from
   ``dash_excalidraw/package-info.json`` — a *different* file, the one
   ``npm run build:backends`` ships into the package. A wheel labelled 0.2.0
   whose ``__version__`` says 0.1.0 is a perfectly working, permanently
   confusing release.
2. **The committed JS bundle stale** relative to the TypeScript it is built
   from — i.e. somebody edited a ``.tsx`` and committed without running
   ``npm run build``. Judged by git commit timestamps, never filesystem
   mtimes: git does not record mtimes, so a fresh clone stamps every file
   with its checkout time and the comparison becomes a coin flip.
3. **The documented Excalidraw version drifting** between ``package.json``
   (what webpack actually bundles) and the shipped ``package-info.json``
   (what the published package advertises). These disagreed at 0.18.1 vs
   ^0.17.6 after the upgrade — invisible, and wrong in the file a consumer
   reads.
4. **CHANGELOG not mentioning the version being released.**
5. **Packaging leaks** — docs-site files, the vendored Clerk tarball, or the
   ``lib/`` tree ending up in a wheel that promises to depend on Dash alone.

    python scripts/check_release.py                    # check
    python scripts/check_release.py --version 0.2.0    # also assert the target

Exit code 0 when clean, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "dash_excalidraw"

problems: list[str] = []
notes: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label:<46} {detail}")
    if not ok:
        problems.append(f"{label}: {detail}")


def _last_commit(*pathspecs: str) -> int | None:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", *pathspecs],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        return int(out.stdout.strip()) if out.stdout.strip() else None
    except Exception:  # noqa: BLE001 — not a git checkout, or no git
        return None


def _tracked(*pathspecs: str) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "--", *pathspecs],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        return [line for line in out.stdout.splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        return []


# What actually ends up in the bundle. webpack's entry is src/ts/index.ts, so
# a file nothing imports is never built — and the jest harness beside the
# component is exactly that: `build:backends` already skips it via
# `--ignore \.test\.`, and `npm run build` after it was added left the bundle
# byte-identical. Comparing commit times against ALL of src/ts therefore reads
# a test-only commit as "the bundle is stale" and fails a release check that
# nothing is wrong with. Measured: adding the harness in d9d615a turned this
# check red in CI while the bundle it was judging had not changed.
_BUNDLE_SOURCES = (
    "src/ts",
    ":(exclude,glob)src/ts/**/*.test.*",
    ":(exclude)src/ts/__mocks__",
)


def check_bundle_freshness(bundle: Path) -> None:
    """Is the committed JS bundle older than the TypeScript it is built from?

    Rebuilding and committing together puts both in the same commit, so equal
    timestamps are the healthy case — hence ``>=``, not ``>``.
    """
    bundle_at = _last_commit(str(bundle.relative_to(ROOT)))
    src_at = _last_commit(*_BUNDLE_SOURCES)

    # A sweep that found nothing and a sweep that swept nothing both give a
    # green here, because `src_at is None` falls through to the SKIP below.
    # Count what the pathspec still sees, so an exclusion that grew too broad
    # is loud instead of silently passing.
    sources = _tracked(*_BUNDLE_SOURCES)
    if not sources:
        check("bundle newer than src/ts", False,
              "no bundle sources matched — the exclusions in _BUNDLE_SOURCES "
              "are too broad, so this check was about to pass on nothing")
        return

    if bundle_at is None or src_at is None:
        notes.append(
            "bundle freshness not checked — no git history here (a tarball "
            "install, or a shallow clone without the relevant commits)."
        )
        print(f"  SKIP  {'bundle newer than src/ts':<46} no git history")
        return

    check("bundle newer than src/ts", bundle_at >= src_at,
          "up to date" if bundle_at >= src_at else
          f"STALE — src/ts committed {src_at - bundle_at}s after the bundle; "
          "run npm run build and commit the result")


def versions() -> dict[str, str]:
    out: dict[str, str] = {}
    out["pyproject.toml"] = re.search(
        r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M
    ).group(1)
    out["package.json"] = json.loads((ROOT / "package.json").read_text())["version"]
    out[f"{PKG}/package-info.json (shipped)"] = json.loads(
        (ROOT / PKG / "package-info.json").read_text()
    )["version"]
    return out


def excalidraw_pins() -> dict[str, str]:
    """The bundled Excalidraw version, as each file states it."""
    out: dict[str, str] = {}
    pj = json.loads((ROOT / "package.json").read_text())
    out["package.json (built)"] = pj["dependencies"]["@excalidraw/excalidraw"]
    pi = json.loads((ROOT / PKG / "package-info.json").read_text())
    dep = (pi.get("dependencies") or {}).get("@excalidraw/excalidraw")
    if dep is not None:
        out[f"{PKG}/package-info.json (advertised)"] = dep
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", help="assert every source reports this version")
    args = ap.parse_args()

    print("\ndash-excalidraw release check\n" + "=" * 66)

    print("\n[versions]")
    vs = versions()
    for name, v in vs.items():
        print(f"        {name:<46} {v}")
    unique = set(vs.values())
    check("all version sources agree", len(unique) == 1,
          "consistent" if len(unique) == 1 else f"differ: {sorted(unique)}")
    target = args.version or vs["pyproject.toml"]
    if args.version:
        check(f"every source is {args.version}", unique == {args.version},
              "ok" if unique == {args.version} else f"found {sorted(unique)}")

    print("\n[excalidraw pin]")
    pins = excalidraw_pins()
    for name, v in pins.items():
        print(f"        {name:<46} {v}")
    # Compared as bare version numbers: package.json pins exactly (0.18.1)
    # while package-info.json may carry a range (^0.18.1). What must never
    # differ is WHICH Excalidraw release this package is about.
    bare = {re.sub(r"^[\^~>=<\s]+", "", v) for v in pins.values()}
    check("package.json and package-info.json name the same Excalidraw",
          len(bare) == 1,
          "consistent" if len(bare) == 1 else f"differ: {sorted(pins.values())}")

    print("\n[build artifacts]")
    bundle = ROOT / PKG / f"{PKG}.js"
    check("JS bundle committed", bundle.exists(),
          f"{bundle.stat().st_size // 1024} KB" if bundle.exists()
          else "MISSING — run npm run build")
    if bundle.exists():
        check_bundle_freshness(bundle)
    generated = ROOT / PKG / "DashExcalidraw.py"
    check("generated component class present", generated.exists(),
          "DashExcalidraw.py" if generated.exists()
          else "MISSING — run npm run build:backends")

    print("\n[changelog]")
    changelog = (ROOT / "CHANGELOG.md").read_text()
    check(f"CHANGELOG mentions {target}", target in changelog,
          "found" if target in changelog else f"add a [{target}] section")
    if "## [Unreleased]" in changelog:
        body = changelog.split("## [Unreleased]", 1)[1].split("## [", 1)[0]
        if body.strip() and "Nothing yet" not in body:
            notes.append(
                "CHANGELOG still has content under [Unreleased] — move it under "
                f"[{target}] before tagging."
            )

    print("\n[packaging]")
    pyproject = (ROOT / "pyproject.toml").read_text()
    check(f"only {PKG} is packaged",
          f'include = ["{PKG}*"]' in pyproject,
          "vendor/, lib/ and docs/ stay out of the wheel")
    check("dash is the only runtime dependency",
          re.search(r'dependencies\s*=\s*\[\s*"dash>=[\d.]+",?\s*\]', pyproject)
          is not None,
          "the docs site's deps live in requirements.txt")
    check("LICENSE present", (ROOT / "LICENSE").exists())
    check("README present", (ROOT / "README.md").exists())

    print("\n[docs site]")
    for f in ("Dockerfile", "render.yaml", "requirements.txt"):
        check(f"{f} present", (ROOT / f).exists())
    reqs = (ROOT / "requirements.txt").read_text()
    check("vendored deps use relative paths", "file:///" not in reqs,
          "no absolute file:// URLs")
    for tarball in re.findall(r"^\./(vendor/\S+)", reqs, re.M):
        check(f"{tarball} committed", (ROOT / tarball).exists())

    print("\n" + "=" * 66)
    for n in notes:
        print(f"NOTE: {n}")
    if problems:
        print(f"\n{len(problems)} problem(s) — not ready to tag:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"\nClean. Ready to tag v{target}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
