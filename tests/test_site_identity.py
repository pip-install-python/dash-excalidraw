"""Site identity: one brand, every surface, verbatim.

The network standard says a site states what it is in the same words
everywhere an agent or a reader can reach. The failure this pins is silent,
which is why it needs tests rather than a code review: nothing errors when a
surface falls back to a default. On this host, before `SITE_BRAND` existed,
the llms viewer's brand chip read a bare **"Dash"** — the `Dash()`
constructor's default title, leaking out as the public identity of a
production documentation site.

dash-improve-my-llms 2.3.4's `resolve_site_title` is what makes the fix
possible: it takes the home page's registered `name` first, `app.title`
second, and *skips* generic candidates ("Home", "Index", "Dash") rather than
publishing them. These tests assert both ends of that — the inputs this repo
controls, and the H1 it produces.
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import REPO_ROOT
from lib.constants import (
    PAGE_TITLE_PREFIX,
    SITE_BRAND,
    SITE_DESCRIPTION,
    SITE_SHORT_NAME,
)

# Spelled out rather than imported, so that renaming the constant cannot
# silently rename the site. Changing the brand should require changing this
# line, deliberately.
EXPECTED_BRAND = "dash-excalidraw — Excalidraw drawing canvas for Dash"


def test_brand_constant_is_the_agreed_identity():
    assert SITE_BRAND == EXPECTED_BRAND


def test_app_title_is_the_brand(app):
    """`Dash(title=...)` — the <title> and `resolve_site_title`'s fallback."""
    assert app.title == EXPECTED_BRAND


def test_home_prose_opens_with_the_brand():
    first = (REPO_ROOT / "pages" / "home.md").read_text().splitlines()[0]
    assert first == f"# {EXPECTED_BRAND}"


def test_llms_index_h1_is_the_brand(client):
    """The single most-read line of this site, and the one nobody looks at."""
    response = client.get("/llms.txt")
    assert response.ok
    assert response.text.splitlines()[0] == f"# {EXPECTED_BRAND}"


def test_llms_index_tagline_is_the_description(client):
    body = client.get("/llms.txt").text
    assert f"> {SITE_DESCRIPTION}" in body


def test_the_viewer_brand_chip_is_not_a_framework_default(client):
    """The chip that read "Dash" on the pre-2.3.4 artifact.

    It is rendered from the same `resolve_site_title` call as the H1, so
    asserting the brand is present and the default is absent catches both a
    stale package and a regressed constant.
    """
    import html as html_module

    from conftest import BROWSER_ACCEPT

    page = client.get("/commands/llms.txt", accept=BROWSER_ACCEPT).text
    # The banner is templated markup, so the brand arrives escaped — the
    # apostrophe in "network's" becomes `&#x27;`. Comparing the raw string
    # here would fail for a reason that has nothing to do with identity.
    assert html_module.escape(EXPECTED_BRAND) in page, (
        "the viewer banner does not name this site"
    )


def test_the_package_name_is_in_the_description_not_the_brand():
    """Naming rules from the standard — note the LIBRARY variant.

    The template's own rule keeps its package name out of the brand, because
    nobody installs a template. A library satellite inverts exactly that half:
    the standard says the package name comes FIRST in the brand, so someone
    who sees the card knows what to `pip install`. Compare the live fleet —
    "dash-leaflet2 — Leaflet 2 maps for Dash", "Dash Email".

    The byline half does NOT invert. "Pip Install Python" is who made it, never
    what the site is called; a brand of the byline would make every satellite
    in the network share one name.
    """
    assert "dash-excalidraw" in SITE_BRAND, (
        "library satellites lead with the package name — see STANDARD.md §1"
    )
    assert "dash-excalidraw" in SITE_DESCRIPTION
    assert "Pip Install Python" in SITE_DESCRIPTION
    assert "Pip Install Python" not in SITE_BRAND


def test_no_surface_falls_back_to_a_generic_title():
    """The values `resolve_site_title` is designed to skip.

    If the brand were ever set to one of these, the package would silently
    fall through to the next candidate and this repo would have no idea which
    string it was publishing.
    """
    from dash_improve_my_llms.handlers import _GENERIC_SITE_TITLES

    assert SITE_BRAND.strip().lower() not in _GENERIC_SITE_TITLES


def test_readme_and_docs_agree_with_the_brand():
    """A README that names the site differently is the next drift."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert EXPECTED_BRAND in readme, "README.md does not state the site brand"


def test_llms_package_floor_is_the_network_standard():
    """Identity resolution lives in the package; the floor is what delivers it."""
    import dash_improve_my_llms as pkg

    parts = tuple(int(p) for p in pkg.__version__.split(".")[:3] if p.isdigit())
    assert parts >= (2, 3, 4), (
        f"dash-improve-my-llms {pkg.__version__} predates resolve_site_title; "
        "the viewer chip and the /llms.txt H1 would fall back to app.title"
    )


# ---------------------------------------------------------------------------
# The per-page title — a share-card surface, not just a browser tab
#
# Dash passes each page's `title` straight into `og:title` and `twitter:title`
# (dash/_pages.py `_page_meta_tags`). PAGE_TITLE_PREFIX therefore sets the
# headline of every unfurl this site produces, and it read the FORK SOURCE's
# brand ("Dash Pip Components | ") in production until 1.2.2 — while every
# other surface correctly said this site's name. Nobody sees their own share
# cards, so only a test catches it.
# ---------------------------------------------------------------------------


def test_the_page_title_prefix_is_this_site():
    assert PAGE_TITLE_PREFIX == f"{SITE_SHORT_NAME} | "
    assert "Dash Pip Components" not in PAGE_TITLE_PREFIX, (
        "the fork source's brand is back in every share card"
    )


def test_the_short_name_cannot_drift_from_the_brand():
    """Two constants, one identity. Derived, so this should be automatic."""
    assert SITE_BRAND.startswith(SITE_SHORT_NAME)


def test_the_share_card_headline_names_this_site(client):
    """og:title and twitter:title, as a scraper reads them."""
    html = client.get("/").text
    for tag in ("og:title", "twitter:title"):
        found = re.findall(
            rf'<meta[^>]*property="{tag}"[^>]*content="([^"]*)"', html
        )
        assert found, f"no {tag} on the home page"
        for value in found:
            assert "Dash Pip Components" not in value, (
                f"{tag}={value!r} advertises the fork source"
            )
            assert SITE_SHORT_NAME in value, f"{tag}={value!r} does not name this site"


def test_no_surface_still_carries_the_fork_source_brand():
    """A sweep, because the prefix was not the only place it could hide."""
    offenders = []
    for path in ("lib/constants.py", "templates/index.html", "pages/home.md",
                 "assets/favicon/site.webmanifest"):
        text = (REPO_ROOT / path).read_text()
        # The constants file documents the old value in a comment explaining
        # the fix; that is the one legitimate mention.
        stripped = re.sub(r"#.*", "", text) if path.endswith(".py") else text
        stripped = re.sub(r"<!--.*?-->", "", stripped, flags=re.S)
        if "Dash Pip Components" in stripped:
            offenders.append(path)
    assert offenders == [], f"the fork source's brand survives in {offenders}"


def test_home_markdown_is_not_a_stale_copy_of_the_old_opening():
    """`# Welcome to:` was the old H1 — an identity that named nothing."""
    body = Path(REPO_ROOT / "pages" / "home.md").read_text()
    assert "# Welcome to:" not in body


# ---------------------------------------------------------------------------
# The header wordmark
# ---------------------------------------------------------------------------


def _header_title_node(app_module):
    """The `#dash-docs-title` node out of the serialised app layout."""
    import json

    from dash._utils import to_json

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("props"), dict) and \
                    node["props"].get("id") == "dash-docs-title":
                yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    hits = list(walk(json.loads(to_json(app_module.app.layout))))
    assert len(hits) == 1, f"expected exactly one #dash-docs-title, got {len(hits)}"
    return hits[0]


def test_the_header_wordmark_is_this_site_read_from_the_constant(app_module):
    node = _header_title_node(app_module)
    assert node["props"]["children"] == SITE_SHORT_NAME, (
        "the header advertises a name that is not this site's — the template "
        "shipped 'Dash Docs' hard-coded, which is how a fork ends up "
        "advertising its parent"
    )


def _home_anchor(app_module):
    """The BRANDED home link in the header (logo + wordmark), not the nav's."""
    import json

    from dash._utils import to_json

    def walk(node):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    tree = json.loads(to_json(app_module.app.layout))
    hits = [n for n in walk(tree)
            if n.get("type") == "Anchor"
            and (n.get("props") or {}).get("href") == "/"
            and any(m.get("type") == "Img" for m in walk(n))]
    assert len(hits) == 1, f"expected one branded home anchor, got {len(hits)}"
    return hits[0]


def test_the_home_link_has_an_accessible_name_on_phones(app_module):
    """Below 576px the wordmark is `display: none`, so it names nothing.

    This is the correction to a wrong claim: `visibleFrom` keeps the node in
    the DOM (which is why the typing animation still finds it), but the
    generated CSS is a `display: none` media query — and a display:none
    subtree is removed from the accessibility tree entirely. So under the
    breakpoint the wordmark contributes no text, and with a decorative logo
    beside it the home link would have NO accessible name at all: a screen
    reader announces "link", and nothing says where it goes.

    The name therefore lives on the anchor, permanently, at every width.
    """
    props = _home_anchor(app_module)["props"]
    label = (props.get("aria-label") or "").strip()
    assert label, (
        "the branded home link has no aria-label — under 576px it has no "
        "accessible name at all, because the wordmark is display:none there"
    )
    assert SITE_SHORT_NAME in label, f"the home link is named {label!r}, not this site"


def test_the_header_logo_is_decorative(app_module):
    """`alt=""`, so it does not compete with the anchor's own name.

    The logo sits INSIDE the labelled link. Giving it alt text too would make
    a screen reader announce the destination twice, and the alt would fight
    the aria-label over which one is the accessible name.
    """
    anchor = _home_anchor(app_module)

    def walk(node):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    imgs = [n for n in walk(anchor) if n.get("type") == "Img"]
    assert imgs, "the branded home link lost its logo"
    for img in imgs:
        assert img["props"].get("alt") == "", (
            'the header logo must be decorative (alt="") — it sits inside a '
            "link that already carries its own aria-label"
        )


def test_the_meta_description_fits_a_search_snippet():
    """~155 chars. Longer is not merely clipped — it is REPLACED.

    Google truncates around 155-160 characters and, for a description it
    judges too long or not representative, rewrites the snippet from page
    text instead. So an over-long description forfeits the snippet rather
    than shortening it. Found at 270 chars by an outside SEO audit.
    """
    assert len(SITE_DESCRIPTION) <= 160, (
        f"SITE_DESCRIPTION is {len(SITE_DESCRIPTION)} chars; Google will "
        "truncate and likely rewrite the snippet. Keep it at or under 160."
    )
    assert len(SITE_DESCRIPTION) >= 90, (
        f"SITE_DESCRIPTION is only {len(SITE_DESCRIPTION)} chars — too thin "
        "to earn the snippet at all."
    )


def test_the_keywords_describe_this_component_not_the_template():
    """The tag shipped naming a documentation boilerplate, never Excalidraw.

    Google has ignored `keywords` since 2009, but Bing and several AI crawlers
    still read it — and whatever reads it was being told this site is about
    Dash Mantine Components and markdown docs. The failure worth guarding is
    not "the tag is absent", it is "the tag describes the wrong product".
    """
    import re

    html = (REPO_ROOT / "templates" / "index.html").read_text()
    match = re.search(r'<meta name="keywords" content="([^"]*)"', html)
    assert match, "the keywords meta tag is gone"
    terms = {t.strip().lower() for t in match.group(1).split(",")}
    for required in ("excalidraw", "whiteboard"):
        assert any(required in t for t in terms), (
            f"the keywords never mention {required!r}: {sorted(terms)}"
        )
    for template_leftover in ("dash mantine components", "markdown docs",
                              "technical documentation", "developer tools"):
        assert template_leftover not in terms, (
            f"the template's keyword {template_leftover!r} is still here — "
            "this tag should describe the component, not the docs framework"
        )


def test_the_header_wordmark_is_hidden_on_phone_widths(app_module):
    """`dash-excalidraw` is a long wordmark for an xs viewport.

    Beside it sit a burger, a 36px logo, a search control and the theme
    toggle, and on a phone in portrait that row overflowed. `visibleFrom`
    renders a CSS class rather than removing the component, which is what
    keeps `assets/text_animation.js` able to find `#dash-docs-title` to type
    into — so this pins the mechanism, not just the outcome.
    """
    node = _header_title_node(app_module)
    assert node["props"].get("visibleFrom") == "xs", (
        "the header wordmark lost its responsive guard — it will overflow "
        "the header row below 576px again"
    )


# ---------------------------------------------------------------------------
# Version claims are DERIVED, never written. "Powered by dash-improve-my-llms
# 2.3.4" served on /llms.txt for months on the reference host while a newer
# package was actually running the site — the most-read surface in the
# network publishing a false fact about itself. Prose writes
# {{VERSION:<distribution>}} (any installed package — this satellite can use
# it for `dash-excalidraw` itself); pages/markdown.py substitutes the
# installed version via lib/versions.py before any consumer sees the text.
#
# This host declares no version in prose today. The tests below are still
# the right ones to carry: the sweep is what keeps it that way, and the
# mechanism tests are what make writing a placeholder safe the first time
# someone does. The template's extra assertion — that /llms.txt's
# "Powered by" line reports the installed package — is deliberately NOT
# ported: there is no such line here, so it would assert prose rather than
# behaviour.
# ---------------------------------------------------------------------------


def test_no_source_markdown_hardcodes_a_package_version():
    """The placeholder is the only way prose may state a package version.

    Sweeps the SOURCE files, so a hardcoded number is caught even on pages
    these tests never fetch. CHANGELOGs and history-narrating docs may name
    versions in context ("until 2.3.4 landed"), and install floors
    (`pkg>=2.5.1`) are requirements, not claims; what prose may not do is
    claim a version as current — which always takes the bold form the
    'Powered by' lines use, next to the package's name or PyPI link.
    """
    claim = re.compile(
        r"(dash-improve-my-llms|dash-excalidraw|pypi\.org/project/)"
        r"[^\n]*?\*\*\d+\.\d+(\.\d+)?\*\*"
    )
    offenders = []
    for md in [REPO_ROOT / "pages" / "home.md", *(REPO_ROOT / "docs").rglob("*.md")]:
        for line in md.read_text().splitlines():
            if claim.search(line):
                offenders.append(f"{md.relative_to(REPO_ROOT)}: {line.strip()[:80]}")
    assert offenders == [], f"hardcoded package versions in prose: {offenders}"


def test_version_placeholder_never_leaks_unsubstituted(client):
    for path in ("/llms.txt", "/", "/commands/llms.txt"):
        body = client.get(path).text
        assert "{{DIMLL_VERSION}}" not in body, f"unsubstituted placeholder on {path}"
        assert "{{VERSION:" not in body, f"unsubstituted placeholder on {path}"


def test_substitution_works_for_any_installed_distribution():
    """The generic form is what lets every satellite state ITS package's
    version — the mechanism must not be special-cased to one package."""
    from importlib.metadata import version

    from lib.versions import substitute_versions

    assert substitute_versions("dash **{{VERSION:dash}}**") == (
        f"dash **{version('dash')}**"
    )


def test_legacy_placeholder_still_resolves():
    """{{DIMLL_VERSION}} predates the generic form; forks may still write it."""
    import dash_improve_my_llms as pkg

    from lib.versions import substitute_versions

    assert substitute_versions("{{DIMLL_VERSION}}") == pkg.__version__


def test_a_version_claim_for_an_absent_package_fails_the_boot():
    """A claim that cannot be true must fail loudly at load time, not leak."""
    import pytest

    from lib.versions import substitute_versions

    with pytest.raises(LookupError, match="not-a-real-distribution"):
        substitute_versions(
            "{{VERSION:not-a-real-distribution}}", source="docs/x.md"
        )


def test_code_examples_keep_the_placeholder_syntax_verbatim():
    """A doc that SHOWS the syntax in a fence must not have it substituted —
    that would render the example as a number and undocument the mechanism."""
    from lib.versions import substitute_versions

    fenced = "```markdown\n**{{VERSION:dash}}**\n```\n"
    assert substitute_versions(fenced) == fenced
    inline = "write `{{VERSION:dash}}` in prose"
    assert substitute_versions(inline) == inline
