"""One fleet Python — image, workflows, render.yaml and healthz must agree.

Found by the ops seat reading the template's tree, not a report (2026-08-25):
the Dockerfile said ``python:3.11.8-slim`` — a PATCH pin, so the image never
received a 3.11.x security release — while the CI matrix said 3.12 and
render.yaml said 3.12.0. Three declared Pythons, a docker boot/battery
testing an interpreter the matrix never ran, and nothing on the wire able to
contradict any of them. These pins hold every encoding to ONE minor, sourced
from the Dockerfile's FROM tag; ``/healthz``'s ``python`` field plus the
``python_matches_declared`` battery check (``scripts/network_smoke.py``) hold
the SERVING host to the same one.

Adapted from the template's reference at 1.6.29 (SYNC-1.6.22-1.6.29 item 5)
for a repo that carries TWO Pythons legitimately, which the reference
anticipates and tells a fork to scope for:

* the **SITE lane** — every job that installs ``requirements.txt`` or boots
  ``run.py``, plus every singleton that lints or audits the site's tree — is
  held to the image's minor. That is the Python a visitor's request actually
  runs on.
* the **PACKAGE lane** — ``package-python-range`` in ``ci.yml`` — tests the
  wheel's ``requires-python`` claim across 3.9-3.13 and is deliberately NOT
  the fleet Python. Pinning it to a container base would fail the moment the
  image moved, and would delete the only measurement of a promise this repo
  publishes on PyPI.

The split is drawn where it is because of what each number MEASURES. A
singleton ``python-version:`` literal measures nothing — it is a choice, and
a choice that differs from the fleet Python is the drift this file exists to
kill, which is why every literal in all three workflows is asserted here
including the wheel-build jobs. ``package-python-range``'s matrix is the one
place a Python is an assertion about the world, so it is checked against
``pyproject.toml`` instead of against the image.

What is deliberately NOT here: no comparison of the RUNNING interpreter to
the fleet minor — the suite legitimately runs on the adjacent window legs
(the matrix's 3.13/3.12 rows), where that assertion would be false by design.
Image-vs-declaration is the battery's job, against a host.

Session-class, never block cargo: it presumes a Dockerfile and a render.yaml,
which not every fork carries.
"""
from __future__ import annotations

import re

import yaml

from conftest import REPO_ROOT

WORKFLOWS = (".github/workflows/ci.yml",
             ".github/workflows/cd.yml",
             ".github/workflows/release.yml")

# The one matrix whose Python is a MEASUREMENT rather than a choice: it
# installs the built wheel and nothing else, to test what pyproject.toml
# claims in `requires-python`. Everything else in this repo's workflows is
# the site lane.
PACKAGE_MEASURED_JOB = "package-python-range"


def _fleet_minor() -> str:
    """The single source: the Dockerfile's FROM tag."""
    for line in (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        m = re.match(r"FROM\s+python:(\S+)", line)
        if m:
            return m.group(1)
    raise AssertionError("Dockerfile has no `FROM python:` line")


def _minor() -> str:
    return _fleet_minor().removesuffix("-slim")


def _workflow(path: str) -> dict:
    return yaml.safe_load((REPO_ROOT / path).read_text(encoding="utf-8"))


def _uncommented(path: str) -> list[str]:
    return [
        ln for ln in (REPO_ROOT / path).read_text(encoding="utf-8").splitlines()
        if not ln.lstrip().startswith("#")
    ]


def _render_runtime() -> str:
    for ln in _uncommented("render.yaml"):
        m = re.match(r"\s*runtime:\s*(\S+)", ln)
        if m:
            return m.group(1)
    raise AssertionError("render.yaml declares no `runtime:`")


def _literals() -> list[tuple[str, str, str]]:
    """(workflow, job, version) for every LITERAL python-version pin.

    Read from the parsed YAML, not by grep: a version number quoted inside a
    comment is exactly the marker-in-comment trap the template's own notes
    warn about, and it cuts both ways — a grep can be satisfied by a line
    that never runs, and defeated by one that does.
    """
    found = []
    for path in WORKFLOWS:
        for job, spec in (_workflow(path).get("jobs") or {}).items():
            for step in spec.get("steps") or []:
                version = (step.get("with") or {}).get("python-version")
                if isinstance(version, str) and re.fullmatch(r"[\d.]+", version):
                    found.append((path, job, version))
    return found


def _matrices() -> dict[str, list[str]]:
    """job -> the matrix's main `python:` list, for jobs that declare one."""
    out = {}
    for path in WORKFLOWS:
        for job, spec in (_workflow(path).get("jobs") or {}).items():
            matrix = (spec.get("strategy") or {}).get("matrix") or {}
            if "python" in matrix:
                out[job] = [str(v) for v in matrix["python"]]
    return out


def _legs() -> dict[str, list[str]]:
    """job -> the pythons its matrix `include:` rows pin."""
    out = {}
    for path in WORKFLOWS:
        for job, spec in (_workflow(path).get("jobs") or {}).items():
            matrix = (spec.get("strategy") or {}).get("matrix") or {}
            rows = [str(r["python"]) for r in (matrix.get("include") or [])
                    if "python" in r]
            if rows:
                out[job] = rows
    return out


def test_dockerfile_tag_is_minor_only():
    """The patch pin IS the security bug: `3.11.8-slim` never receives a
    3.11.x fix release. The minor tag tracks them through Docker Hub."""
    tag = _fleet_minor()
    assert re.fullmatch(r"\d+\.\d+-slim", tag), (
        f"Dockerfile FROM tag is {tag!r} — must be a MINOR tag "
        "(python:X.Y-slim), never a patch pin"
    )


def test_render_yaml_agrees_with_the_image():
    """BRANCHES on the service runtime.

    `runtime: python` — the native runtime reads PYTHON_VERSION and requires
    a full X.Y.Z (its encoding, not ours): the value is REQUIRED and its
    MINOR must be the fleet Python.

    `runtime: docker` — which is this service — NOTHING reads PYTHON_VERSION;
    the image is the interpreter. The key must be ABSENT: a value there reads
    like the platform's setting and can never be true, which is this item's
    own defect class arriving through its fix. If this service's runtime ever
    changes, the test flips branches by itself.
    """
    minor = _minor()
    runtime = _render_runtime()
    lines = _uncommented("render.yaml")
    value = None
    for i, ln in enumerate(lines):
        if re.match(r"\s*- key: PYTHON_VERSION$", ln):
            m = re.search(r'value:\s*"([^"]+)"', lines[i + 1])
            value = m and m.group(1)
            break
    if runtime == "docker":
        assert value is None, (
            f"render.yaml declares PYTHON_VERSION {value!r} on a docker "
            "runtime — nothing reads it there; a string that looks like the "
            "platform's setting and can never be true is the drift class "
            "this file exists to kill. Delete the key."
        )
        return
    assert runtime == "python", (
        f"render.yaml runtime is {runtime!r} — this test knows `python` and "
        "`docker`; extend the branch deliberately"
    )
    assert value, "render.yaml declares no PYTHON_VERSION"
    assert re.fullmatch(r"\d+\.\d+\.\d+", value), (
        f"PYTHON_VERSION {value!r} — Render requires full X.Y.Z"
    )
    assert value.startswith(minor + "."), (
        f"render.yaml PYTHON_VERSION {value} vs image python:{minor}-slim — "
        "the native-runtime lane and the image lane disagree"
    )


def test_every_workflow_python_literal_is_the_fleet_python():
    """Singleton pins are choices, so they all take the same one.

    Including the two wheel-build jobs: the wheel is `py3-none-any` and
    check_release.py is stdlib, so nothing about those numbers is a claim —
    which makes a divergent value pure drift, indistinguishable from the
    3.11.8/3.12/3.12.0 tangle this file was written for.
    """
    minor = _minor()
    literals = _literals()
    assert literals, "no literal python-version pins found — workflows moved?"
    wrong = [(w, j, v) for w, j, v in literals if v != minor]
    assert not wrong, (
        f"image is python:{minor}-slim but these jobs pin another Python: "
        + ", ".join(f"{w}:{j} -> {v}" for w, j, v in wrong)
    )


def test_the_site_lane_matrix_mains_are_the_fleet_python():
    """`test` and `docs-compat` install requirements.txt and boot the app —
    their main row is what "the docs site's Python" means."""
    minor = _minor()
    matrices = _matrices()
    assert matrices, "no python matrices found — ci.yml restructured?"
    site = {job: rows for job, rows in matrices.items()
            if job != PACKAGE_MEASURED_JOB}
    assert site, (
        "every python matrix is classed as the package lane — the site lane "
        "cannot be empty on a repo that deploys a site"
    )
    wrong = {job: rows for job, rows in site.items() if rows != [minor]}
    assert not wrong, (
        f"site-lane matrix mains {wrong} vs image python:{minor}-slim"
    )


def test_site_matrix_legs_are_the_adjacent_minors():
    """The compat window stays three wide: include legs are X.Y-1 and X.Y-2
    (or X.Y+1 once it exists). The package lane's legs are exempt — they
    measure `requires-python`, and holding them to a container base would
    fail the moment the image moved."""
    major, y = (int(p) for p in _minor().split("."))
    allowed = {f"{major}.{y}", f"{major}.{y - 1}", f"{major}.{y - 2}",
               f"{major}.{y + 1}"}
    legs = {job: rows for job, rows in _legs().items()
            if job != PACKAGE_MEASURED_JOB}
    assert legs, "no site-lane include legs — the window collapsed to one"
    outside = {job: [leg for leg in rows if leg not in allowed]
               for job, rows in legs.items()}
    outside = {job: bad for job, bad in outside.items() if bad}
    assert not outside, (
        f"site-lane matrix legs {outside} fall outside the three-wide window "
        f"around {major}.{y}"
    )


def test_the_package_lane_measures_what_pyproject_claims():
    """The one Python here that is an assertion about the world.

    `package-python-range` installs the built wheel on every interpreter
    pyproject.toml advertises, which is what makes `requires-python` measured
    rather than asserted. Checked against the classifiers, never against the
    image: adding a classifier without a matrix leg publishes a promise
    nothing tests, and adding a leg without a classifier tests a promise
    nobody made.
    """
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    claimed = sorted(
        re.findall(r'"Programming Language :: Python :: (\d+\.\d+)"', pyproject),
        key=lambda v: tuple(int(p) for p in v.split(".")),
    )
    assert claimed, "pyproject.toml lists no per-minor Python classifiers"

    tested = _matrices().get(PACKAGE_MEASURED_JOB)
    assert tested is not None, (
        f"ci.yml has no `{PACKAGE_MEASURED_JOB}` job — the wheel's "
        "requires-python claim is no longer measured anywhere"
    )
    assert sorted(tested, key=lambda v: tuple(int(p) for p in v.split("."))) == claimed, (
        f"{PACKAGE_MEASURED_JOB} tests {tested} but pyproject.toml claims "
        f"{claimed} — one of them is lying to PyPI"
    )


def test_healthz_reports_the_serving_interpreter():
    """The observability half. Absence is NOT-ADOPTED, never
    not-applicable (spec item 5's detect, amended 1.6.28): emojimart's image
    moved to 3.14 via dependabot alone, so the cheap half of the detect
    passed while the expensive half failed invisibly.

    The value is deliberately NOT compared to the fleet minor — this suite
    runs on the window legs by design. `python_matches_declared` in
    scripts/network_smoke.py makes that comparison, against a host.
    """
    from lib.health import health_payload

    served = health_payload("flask").get("python")
    assert served, "/healthz carries no `python` field"
    assert re.fullmatch(r"\d+\.\d+\.\d+.*", served), (
        f"/healthz reports python={served!r} — not a version string"
    )
