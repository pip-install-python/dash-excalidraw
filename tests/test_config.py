"""Configuration that is silently wrong when it's wrong: base URL, template
metadata, and the version numbers that live in more than one file."""

from __future__ import annotations

import json
import re

import pytest

from conftest import REPO_ROOT
from lib import constants

INDEX_HTML = (REPO_ROOT / "templates" / "index.html").read_text()

# The template is heavily commented, and several comments quote the very tags
# they are explaining. Scanning for live markup has to ignore them.
INDEX_HTML_LIVE = re.sub(r"<!--.*?-->", "", INDEX_HTML, flags=re.S)


# ---------------------------------------------------------------------------
# BASE_URL guard
# ---------------------------------------------------------------------------


def test_default_base_url_is_the_public_domain():
    assert constants.DEFAULT_BASE_URL == "https://excalidraw.2plot.dev"
    assert not constants.DEFAULT_BASE_URL.endswith("/")


def test_guard_is_inert_outside_production(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    constants.require_owned_base_url()  # must not raise locally or in CI


def test_guard_rejects_an_unset_base_url_in_production(monkeypatch):
    """A fork that deploys without setting APP_BASE_URL would serve the
    boilerplate's canonical on every page and ask to be deindexed."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="APP_BASE_URL"):
        constants.require_owned_base_url()


def test_guard_rejects_platform_hostnames(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("APP_BASE_URL", "https://my-docs.onrender.com")
    with pytest.raises(RuntimeError, match="platform-generated"):
        constants.require_owned_base_url("https://my-docs.onrender.com")


def test_guard_accepts_a_real_domain(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("APP_BASE_URL", "https://leaflet.2plot.dev")
    constants.require_owned_base_url("https://leaflet.2plot.dev")


# ---------------------------------------------------------------------------
# index.html
# ---------------------------------------------------------------------------


def test_template_has_no_hardcoded_canonical():
    """The package injects a per-page canonical. A second one in the template
    doesn't override it — both ship, and a conflicting pair is no signal."""
    live = re.findall(r'<link[^>]+rel="canonical"[^>]*>', INDEX_HTML_LIVE)
    assert live == [], f"remove the hard-coded canonical: {live}"


def test_template_has_no_placeholder_hosts():
    for placeholder in ("yourdomain.com", "onrender.com", "Your Organization Name",
                        "Your Name or Organization", "plotly.pro"):
        assert placeholder not in INDEX_HTML, f"{placeholder!r} left in templates/index.html"


def test_template_references_only_assets_that_exist():
    """A <link> or <meta> pointing at a missing asset is a 404 on every page
    load — invisible in a browser, noisy in the logs, and a broken preview
    card on every share."""
    referenced = set(
        re.findall(
            r'["\'(](?:https://boilerplate\.2plot\.dev)?/assets/([^"\')\s]+)',
            INDEX_HTML_LIVE,
        )
    )
    missing = {name for name in referenced if not (REPO_ROOT / "assets" / name).exists()}
    assert not missing, f"index.html references assets that do not exist: {sorted(missing)}"


def test_structured_data_parses():
    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', INDEX_HTML, re.S
    )
    assert len(blocks) >= 2, "expected Organization and SoftwareApplication JSON-LD"
    for block in blocks:
        json.loads(block)  # raises on malformed markup


def test_declared_software_version_matches_constants():
    """Two places hold the version; they drift the moment one is bumped alone."""
    blocks = re.findall(
        r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', INDEX_HTML, re.S
    )
    versions = [
        json.loads(b)["softwareVersion"] for b in blocks if "softwareVersion" in b
    ]
    assert versions == [constants.APP_VERSION], (
        f"index.html declares softwareVersion {versions}, lib/constants.py says "
        f"{constants.APP_VERSION}"
    )


# ---------------------------------------------------------------------------
# The title element
#
# dash-improve-my-llms locates it with `re.compile(r"<title>.*?</title>",
# DOTALL | IGNORECASE)` and rewrites the first match. Two ways that goes
# wrong, both silent:
#
#   - No element at all: nothing to anchor on, so no page gets a title.
#   - The tag name written in angle brackets inside a nearby comment: the
#     match starts THERE and runs to the next closing tag, so every line in
#     between is replaced by the rewritten title and disappears from the
#     served page. With rewriting on it still looks correct.
# ---------------------------------------------------------------------------

TITLE_RE = re.compile(r"<title>.*?</title>", re.S | re.I)


def test_template_uses_the_dash_title_placeholder():
    """A hard-coded title discards the per-page titles pages/markdown.py
    registers, and makes every page depend on the package rewriting it."""
    assert "<title>{%title%}</title>" in INDEX_HTML


def test_only_one_title_match_and_it_is_the_element():
    """Guards the comment trap in both directions."""
    matches = TITLE_RE.findall(INDEX_HTML)
    assert matches == ["<title>{%title%}</title>"], (
        "the title regex matched something other than the element itself — "
        "check for the tag name written in angle brackets inside a comment"
    )


def test_no_title_tag_spelled_out_in_comments():
    for comment in re.findall(r"<!--.*?-->", INDEX_HTML, re.S):
        assert "<title" not in comment.lower(), (
            "a comment spells the title tag in angle brackets; the package's "
            "regex would start matching there and swallow the lines that follow"
        )


def test_app_title_is_set(app_module):
    """`{%title%}` resolves to app.title in the served HTML. Unset, Dash's
    default is the bare string "Dash" on every page."""
    assert app_module.app.title == constants.APP_TITLE
    assert constants.APP_TITLE != "Dash"


def test_no_dead_llm_endpoints_advertised():
    """/page.json and /architecture.txt were removed in dash-improve-my-llms
    2.0. Advertising them points agents at two 404s."""
    for dead in ("/page.json", "/architecture.txt", "/llms.toon"):
        assert dead not in INDEX_HTML_LIVE, (
            f"{dead} is no longer served but is still advertised"
        )


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def test_the_installed_package_meets_the_floor(app_module):
    """Fail with the reason, not with thirty downstream symptoms.

    An IDE run configuration pointing at another project's virtualenv starts
    this app quite happily against whatever versions that environment holds.
    On dash-improve-my-llms 2.0.0 there is no `llms_viewer.py` at all, so
    `/<page>/llms.txt` serves plain Markdown to everyone and the negotiation
    tests below fail in a way that reads like a bug in the app. It isn't; it's
    the interpreter.
    """
    import sys

    import dash_improve_my_llms as pkg

    installed = tuple(int(p) for p in pkg.__version__.split(".")[:3] if p.isdigit())
    assert installed >= app_module.LLMS_PKG_FLOOR, (
        f"dash-improve-my-llms {pkg.__version__} is below the "
        f"{app_module.LLMS_PKG_FLOOR} floor. Running from {sys.executable} — "
        "if that is not this project's .venv, that is the whole problem."
    )


# ---------------------------------------------------------------------------
# Constructor arguments
# ---------------------------------------------------------------------------


def test_mcp_kwargs_are_omitted_when_mcp_is_off(app_module):
    """Dash raises TypeError on unknown constructor keywords.

    `enable_mcp` landed in Dash 4.3, so naming it unconditionally made the app
    refuse to boot on 4.2 with `Dash() got an unexpected keyword argument
    'enable_mcp'` — an error that says nothing about MCP, over a feature that
    is off by default.
    """
    assert app_module.MCP_KWARGS == {}, (
        "MCP is off by default, so no MCP keyword should reach the Dash "
        "constructor at all"
    )


# ---------------------------------------------------------------------------
# Repo hygiene
# ---------------------------------------------------------------------------


# Live links to domains that have been retired. Matching the URL rather than
# the bare hostname on purpose: the changelog has to name plotly.pro in the
# entry that records its removal, and that mention is not a broken link.
RETIRED_LINKS = re.compile(r"https?://(?:www\.)?(plotly\.pro)")

SKIP_DIRS = {".venv", "node_modules", ".git", "__pycache__", ".claude", "vendor", ".idea"}


def test_no_links_to_retired_domains():
    """plotly.pro was retired in favour of 2plot.ai."""
    offenders = []
    for path in REPO_ROOT.glob("**/*"):
        if not path.is_file() or path.suffix not in {".py", ".md", ".html", ".css", ".yml"}:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        for match in RETIRED_LINKS.finditer(path.read_text(errors="ignore")):
            offenders.append(f"{path.relative_to(REPO_ROOT)} -> {match.group(1)}")
    assert offenders == [], f"links to retired domains: {offenders}"


# ---------------------------------------------------------------------------
# Workflow references
#
# This repo's CI was forked from another satellite's and never adapted. Three
# of its jobs called scripts that exist there and not here — smoke_test.py,
# compat_matrix.py, check_release.py — and nothing noticed for the whole life
# of the file, because CI triggers on pull requests and this site lived on a
# branch that was never PR'd. The first run was the first deploy, and it lost
# nine checks to "No such file or directory".
#
# A workflow cannot be unit-tested, but the assumptions it makes about the
# repo can be. These two tests are that.
# ---------------------------------------------------------------------------

WORKFLOWS = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))


def test_every_script_a_workflow_runs_exists():
    """`run: python scripts/x.py` must name a file that is actually here."""
    missing = []
    for wf in WORKFLOWS:
        for ref in set(re.findall(r"scripts/[A-Za-z0-9_]+\.py", wf.read_text())):
            if not (REPO_ROOT / ref).exists():
                missing.append(f"{wf.name} -> {ref}")
    assert missing == [], (
        f"workflows call scripts this repo does not have: {missing}"
    )


def test_no_workflow_names_another_repos_artifacts():
    """A forked workflow that still says `dash_leaflet2` builds, tags and
    publishes the wrong thing — and `SITE_URL` pointing at another live host
    means a deploy of THIS repo smoke-tests THAT one and reports it green."""
    foreign = ("dash_leaflet2", "dash-leaflet2", "leaflet.2plot.dev",
               "boilerplate.2plot.dev", "dash_pannellum", "pannellum.2plot.dev")
    hits = []
    for wf in WORKFLOWS:
        for line_no, line in enumerate(wf.read_text().splitlines(), 1):
            # Prose may name another repo when explaining where something
            # came from; only live YAML may not.
            if line.lstrip().startswith("#"):
                continue
            for name in foreign:
                if name in line:
                    hits.append(f"{wf.name}:{line_no}: {line.strip()[:70]}")
    assert hits == [], f"workflows reference another repo's artifacts: {hits}"


def test_the_dash_pin_carries_the_compat_matrix_marker():
    """CI's docs-compat job strips this line to install one Dash per leg.

    The strip is `grep -v 'COMPAT-MATRIX: dash'`. Without the marker it
    silently matches nothing, requirements.txt reinstates the pin, and every
    leg of the matrix measures the pinned version — the matrix looks green
    and tests one version three times.
    """
    lines = [ln for ln in (REPO_ROOT / "requirements.txt").read_text().splitlines()
             if re.match(r"^dash[~=<>\[]", ln)]
    assert len(lines) == 1, f"expected exactly one dash pin line, got {lines}"
    assert "# COMPAT-MATRIX: dash" in lines[0], (
        f"the dash pin lost its COMPAT-MATRIX marker: {lines[0]!r}"
    )


# ---------------------------------------------------------------------------
# Mobile layout — rules whose absence is invisible until someone opens the
# site on a phone. Each was measured in a real 414px viewport before and
# after; the numbers in the docstrings are those measurements.
# ---------------------------------------------------------------------------

MAIN_CSS = (REPO_ROOT / "assets" / "main.css").read_text()


def test_no_stylesheet_targets_a_mantine_hashed_class():
    """`.m_*` selectors are private, version-unstable build artifacts.

    Nothing guarantees which component a hash names in the next release, and
    a rule that misses simply stops applying — silently — while one that
    starts matching something new applies geometry to the wrong component.
    Audited against DMC 2.8: `.m_5caae85b` had already gone dead (zero
    occurrences in the bundle) and `.m_9cdde9a` was putting a stray 15px
    margin on the AppShell aside.

    2plot_leaflet recorded the same lesson the hard way — a `.m_b8a05bbd`
    rule (the Drawer content) with `!important` overrode the network-standard
    drawer's docking styles and left that host's mobile navigation floating.

    Style Mantine through props, `styles={}`, or the stable
    `.mantine-<Component>-<part>` selectors the Styles API guarantees.
    """
    import re

    for css in (REPO_ROOT / "assets").glob("*.css"):
        text = css.read_text()
        # Strip comments: the removal notice names the old hashes on purpose.
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        hits = re.findall(r"\.m_[0-9a-f]{6,}", text)
        assert hits == [], f"{css.name} targets Mantine hashed classes: {hits}"


def test_markdown_tables_scroll_inside_their_own_box():
    """A `<table>` is min-content sized and will drag the page wide.

    Measured at 414px before this rule: the home page's prop-mapping table
    rendered 471px inside a 318px column and the document scrolled 105px
    horizontally — every paragraph on the page could be swiped sideways.
    After: page overflow 0, the table a 318px box scrolling 471px of content.
    """
    import re

    block = re.search(
        r'\[id\^="m2d-page"\] table:not\(\.mantine-Table-root\)\s*\{([^}]*)\}',
        MAIN_CSS)
    assert block, "the markdown-table scroll rule is gone"
    body = block.group(1)
    for prop in ("display: block", "width: max-content",
                 "max-width: 100%", "overflow-x: auto"):
        assert prop in body, f"the table rule lost `{prop}`"


def test_long_identifiers_in_control_labels_can_break():
    """/ui-options labels a Switch `canvasActions.changeViewBackgroundColor`.

    A dotted identifier offers no break opportunity, so it rendered 309px
    wide in a 250px box and pushed 15px past a 414px viewport. `anywhere`
    is the only value that helps — `break-word` will not break mid-token.
    """
    assert "overflow-wrap: anywhere" in MAIN_CSS, (
        "control labels can no longer break, so a long identifier will "
        "widen the page again"
    )


def test_noscript_block_carries_no_h1():
    """Crawlers run no JavaScript and PARSE noscript content — an h1 there
    becomes a second site-wide h1 on every page, competing with each
    page's own. Found on the llms-2plot-dev fork (2026-08-23), fixed at
    the source; this pins it. HTML comments are stripped first so the
    explanatory comment naming the tag can't trip the check."""
    import re
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "templates" / "index.html").read_text()
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    noscript = re.search(r"<noscript>(.*?)</noscript>", html, re.S)
    assert noscript, "index.html lost its noscript block?"
    assert "<h1" not in noscript.group(1), (
        "the noscript block carries an <h1> — every page now has a second "
        "site-wide h1 in the crawler's parse; use h2/h3 in this block"
    )
