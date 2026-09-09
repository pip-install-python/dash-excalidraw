"""A page may claim THIS repo's own package version without an installed dist.

The regression this pins cost a boot, not a test: `docs/migration` wrote
`{{VERSION:dash-excalidraw}}`, which was green on a developer venv that had
run `pip install -e .` and raised `LookupError` at app construction on CI and
in the Docker image — neither of which runs `pip install .`. The image does
`pip install -r requirements.txt` then `COPY . .`, so `dash_excalidraw` is
imported from the working directory with no dist-info at all.

DIVERGENCES.md #17 records the narrow fallback that fixes it. These tests are
what make a sync that "restores" the template's version go red instead of
shipping a site that cannot boot.
"""

from __future__ import annotations

import importlib.metadata as md

import pytest

from lib import versions


@pytest.fixture
def no_own_distribution(monkeypatch):
    """The CI / Docker condition: every name resolves EXCEPT our own."""
    real = md.version

    def fake(name):
        if str(name).replace("_", "-").lower() == versions._OWN_DIST:
            raise md.PackageNotFoundError(name)
        return real(name)

    # lib.versions binds `version` at import time, so patch the name it holds.
    monkeypatch.setattr(versions, "version", fake)
    return fake


def test_own_package_resolves_from_the_tree(no_own_distribution):
    out = versions.substitute_versions(
        "running {{VERSION:dash-excalidraw}} today", source="probe.md"
    )
    assert "{{VERSION:" not in out, "placeholder leaked into served prose"

    import dash_excalidraw

    assert dash_excalidraw.__version__ in out


def test_the_fallback_agrees_with_the_installed_distribution():
    """With a dist present both paths must give the same answer.

    A fallback that quietly disagreed with the wheel would be worse than the
    LookupError it replaced: every page would publish a number the package
    does not carry.
    """
    import dash_excalidraw

    try:
        installed = md.version(versions._OWN_DIST)
    except md.PackageNotFoundError:
        pytest.skip("no dist-info here — that is CI's condition, not a failure")
    assert installed == dash_excalidraw.__version__


def test_any_other_missing_distribution_still_fails_loudly(no_own_distribution):
    """The narrow scope IS the divergence.

    For a third-party package "not installed" really does mean the claim
    cannot be true, and the template's loud failure is correct there.
    """
    with pytest.raises(LookupError):
        versions.substitute_versions(
            "claims {{VERSION:definitely-not-installed-xyz}}", source="probe.md"
        )


def test_a_real_dependency_still_resolves_through_metadata(no_own_distribution):
    """The fallback must not shadow the normal path."""
    out = versions.substitute_versions(
        "dimll {{VERSION:dash-improve-my-llms}}", source="probe.md"
    )
    assert md.version("dash-improve-my-llms") in out


def test_code_spans_and_fences_are_still_left_verbatim(no_own_distribution):
    """The migration page's pinning section depends on this.

    A fence is not substituted, which is why that section carries no version
    number at all rather than one that would go stale at the next release.
    """
    fenced = "```text\n{{VERSION:dash-excalidraw}}\n```\n"
    assert versions.substitute_versions(fenced, source="probe.md") == fenced

    span = "the `{{VERSION:dash-excalidraw}}` placeholder\n"
    assert versions.substitute_versions(span, source="probe.md") == span
