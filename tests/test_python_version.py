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
anticipates and tells a fork to scope for. The scoping is BY JOB NAME, not
by file: the reference's greps read a whole workflow, and this is the first
repo in the fleet whose ci.yml has a lane that file explicitly disclaims.

* ``SITE_LANE_JOBS`` — every job whose Python is a CHOICE — is held to the
  image's minor: the jobs that install ``requirements.txt`` or boot
  ``run.py``, the singletons that lint and audit this site's tree, and the
  two wheel-build jobs. The wheel is ``py3-none-any`` and check_release.py is
  stdlib, so nothing about those two numbers is a claim — which makes a
  divergent value pure drift, indistinguishable from the 3.11.8/3.12/3.12.0
  tangle this file exists for. DIVERGENCES.md entry 8 records the reading.
* ``PACKAGE_LANE_JOBS`` — ``package-python-range`` — is the one Python here
  that MEASURES something: it installs the built wheel on every interpreter
  ``pyproject.toml`` advertises, which is what makes ``requires-python`` a
  measurement instead of a claim. Deliberately unread by the fleet pins;
  checked against the classifiers instead.

A job that declares a Python and lands in neither set fails
``test_every_job_declaring_a_python_is_classified`` loudly. Silence there
would be the worse failure: an unclassified job is a Python nobody holds to
anything.

The workflows are hand-parsed rather than read with PyYAML, and that is
deliberate: this suite installs the SITE's requirements, where PyYAML is
only a transitive of ``python-frontmatter``. A test that fails with
ImportError the day an upstream swaps its YAML library is a pin that stops
pinning for a reason unrelated to what it pins. Comments are stripped first,
so a version number quoted in a comment can neither satisfy a pin nor
defeat one.

What is deliberately NOT here: no comparison of the RUNNING interpreter to
the fleet minor — the suite legitimately runs on the adjacent window legs
(the matrix's 3.13/3.12 rows), where that assertion would be false by
design. Image-vs-declaration is the battery's job, against a host.

Session-class, never block cargo: it presumes a Dockerfile and a render.yaml,
which not every fork carries.
"""
from __future__ import annotations

import re

from conftest import REPO_ROOT

CI = ".github/workflows/ci.yml"
CD = ".github/workflows/cd.yml"
RELEASE = ".github/workflows/release.yml"
WORKFLOWS = (CI, CD, RELEASE)

# Jobs whose Python is a CHOICE — all held to the image's minor.
SITE_LANE_JOBS = {
    CI: frozenset({"lint", "test", "docs-compat", "docker", "pip-audit",
                   "package"}),
    CD: frozenset({"test", "deploy", "verify"}),
    RELEASE: frozenset({"verify", "build", "publish", "github-release"}),
}

# Jobs whose Python MEASURES the wheel's own `requires-python` window, and
# which these pins therefore do not read. Never empty in this repo: it
# publishes a component from this same tree (DIVERGENCES 1).
PACKAGE_LANE_JOBS = {
    CI: frozenset({"package-python-range"}),
    CD: frozenset(),
    RELEASE: frozenset(),
}


def _fleet_minor() -> str:
    """The single source: the Dockerfile's FROM tag."""
    for line in (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        m = re.match(r"FROM\s+python:(\S+)", line)
        if m:
            return m.group(1)
    raise AssertionError("Dockerfile has no `FROM python:` line")


def _minor() -> str:
    return _fleet_minor().removesuffix("-slim")


def _uncommented(path) -> list[str]:
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


def _jobs(path) -> dict[str, list[str]]:
    """`jobs:` split into name -> its lines, by indentation."""
    jobs: dict[str, list[str]] = {}
    inside = False
    current: str | None = None
    for ln in _uncommented(path):
        if re.match(r"^jobs:\s*$", ln):
            inside = True
            continue
        if not inside:
            continue
        if ln.strip() and not ln.startswith(" "):
            break  # a later top-level key — `jobs:` is over
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", ln)
        if m:
            current = m.group(1)
            jobs[current] = []
            continue
        if current is not None:
            jobs[current].append(ln)
    assert jobs, f"{path}: no `jobs:` mapping parsed"
    return jobs


def _matrix_python(lines) -> list[str]:
    """Every version in the matrix's main `python: [...]` row, in order.

    Any arity: the site lane's row carries one value (the fleet Python) and
    the package lane's carries the whole `requires-python` window.
    """
    for ln in lines:
        m = re.match(r'^\s*python:\s*\[(.+)\]\s*$', ln)
        if m:
            return re.findall(r'"([\d.]+)"', m.group(1))
    return []


def _legs(lines) -> list[str]:
    """The pythons this job's matrix `include:` rows pin."""
    return [m.group(1) for ln in lines
            if (m := re.match(r'^\s*- python:\s*"([\d.]+)"', ln))
            or (m := re.match(r'^\s{10,}python:\s*"([\d.]+)"', ln))]


def _literals(lines) -> list[str]:
    """Singleton `python-version: "X.Y"` pins. `${{ matrix.python }}` is not
    a literal and not a declaration — the matrix rows it reads are."""
    return [m.group(1) for ln in lines
            if (m := re.match(r'^\s*python-version:\s*"([\d.]+)"', ln))]


def _declared(lines) -> list[str]:
    return _matrix_python(lines) + _legs(lines) + _literals(lines)


def _site_jobs(path) -> dict[str, list[str]]:
    jobs = _jobs(path)
    known = SITE_LANE_JOBS[path]
    missing = sorted(known - set(jobs))
    assert not missing, (
        f"{path}: SITE_LANE_JOBS names {missing}, which no longer exist — a "
        "renamed job silently drops out of every pin below. Update the set."
    )
    return {name: jobs[name] for name in sorted(known)}


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


def test_every_job_declaring_a_python_is_classified():
    """The guard on the guard.

    Scoping the pins by job name means an unlisted job is simply not read —
    the right behaviour for the package matrix and the wrong one for a job
    somebody forgot to classify. This test is the difference: every job that
    declares a Python literal must be in exactly one lane.
    """
    for path in WORKFLOWS:
        classified = SITE_LANE_JOBS[path] | PACKAGE_LANE_JOBS[path]
        overlap = SITE_LANE_JOBS[path] & PACKAGE_LANE_JOBS[path]
        assert not overlap, (
            f"{path}: {sorted(overlap)} classified as BOTH lanes — a job "
            "serves one Python's purpose or the other"
        )
        for name, lines in _jobs(path).items():
            declared = _declared(lines)
            if not declared:
                continue
            assert name in classified, (
                f"{path} job {name!r} declares Python {sorted(set(declared))} "
                "and belongs to neither SITE_LANE_JOBS nor PACKAGE_LANE_JOBS. "
                "Classify it: a site-lane job is held to the image's minor, a "
                "package-lane job is the wheel's business and deliberately "
                "unread. An unclassified job is a Python nobody holds to "
                "anything."
            )


def test_site_lane_singletons_and_matrix_mains_are_the_fleet_python():
    """A singleton pin measures nothing — it is a choice, and a divergent
    choice is the drift this file exists for. Same for a matrix's main row:
    it is the Python the job is ABOUT."""
    minor = _minor()
    wrong, seen = [], 0
    for path in WORKFLOWS:
        for name, lines in _site_jobs(path).items():
            for version in _matrix_python(lines) + _literals(lines):
                seen += 1
                if version != minor:
                    wrong.append(f"{path}:{name} -> {version}")
    assert seen, "no site-lane Pythons found at all — workflows restructured?"
    assert not wrong, (
        f"image is python:{minor}-slim but these site-lane jobs pin another "
        "Python: " + ", ".join(wrong)
    )


def test_site_matrix_legs_are_the_adjacent_minors():
    """The compat window stays three wide: include legs are X.Y-1 and X.Y-2
    (or X.Y+1 once it exists). The package lane's legs are exempt — they
    measure `requires-python`, and holding them to a container base would
    fail the moment the image moved."""
    major, y = (int(part) for part in _minor().split("."))
    allowed = {f"{major}.{y}", f"{major}.{y - 1}", f"{major}.{y - 2}",
               f"{major}.{y + 1}"}
    outside, seen = [], 0
    for path in WORKFLOWS:
        for name, lines in _site_jobs(path).items():
            for leg in _legs(lines):
                seen += 1
                if leg not in allowed:
                    outside.append(f"{path}:{name} -> {leg}")
    assert seen, "no site-lane include legs — the window collapsed to one"
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
    order = lambda v: tuple(int(part) for part in v.split("."))  # noqa: E731
    claimed = sorted(
        re.findall(r'"Programming Language :: Python :: (\d+\.\d+)"', pyproject),
        key=order,
    )
    assert claimed, "pyproject.toml lists no per-minor Python classifiers"

    jobs = _jobs(CI)
    tested = sorted(
        {v for name in PACKAGE_LANE_JOBS[CI] for v in _matrix_python(jobs[name])},
        key=order,
    )
    assert tested, (
        f"{sorted(PACKAGE_LANE_JOBS[CI])} declares no python matrix — the "
        "wheel's requires-python claim is no longer measured anywhere"
    )
    assert tested == claimed, (
        f"the package lane tests {tested} but pyproject.toml claims "
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
