"""The navigation contract (1.6.38) — uniform where it must be, free where it may.

Owner's brief of 2026-08-30 (DESIGN-navigation-uniformity): the sidebar's
sections come from frontmatter against CATEGORY_ORDER; the network is ONE
registry rendered as the top bar's Other Apps menu; Resources is one
constant; Admin is owner-only and absent from the tree otherwise; every
icon-only control has a name; no `dcc.*` where DMC has the component. Each
pin here is one line of that brief.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
ALLOWED_DCC = {"Location", "Store", "Interval", "Upload", "Graph"}


def _calls(src: str, name: str):
    """Yield the source text of every `name(` call, parens balanced."""
    for m in re.finditer(re.escape(name) + r"\(", src):
        depth, i = 0, m.start()
        while i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    yield src[m.start():i + 1]
                    break
            i += 1


# ------------------------------------------------------------- a11y --


@pytest.mark.parametrize("control", ["dmc.Burger", "dmc.ActionIcon"])
def test_every_icon_only_control_in_components_has_a_name(control):
    """Requirement 9: the audits named the unlabelled Burger and copy
    button. Every Burger/ActionIcon in components/ carries aria-label."""
    unlabelled = []
    for path in sorted((REPO / "components").glob("*.py")):
        for call in _calls(path.read_text(), control):
            if "aria-label" not in call:
                unlabelled.append(f"{path.name}: {call[:60]}…")
    assert unlabelled == [], unlabelled


def test_code_highlight_copy_button_has_a_name():
    src = (REPO / "lib" / "directives" / "source.py").read_text()
    assert "copyLabel=" in src and "copiedLabel=" in src


def test_no_dcc_where_dmc_has_the_component():
    """Requirement 10, fleet-wide: `dcc.` only for Location, Store,
    Interval, Upload, Graph (no DMC equivalent)."""
    offenders = []
    for folder in ("pages", "components"):
        for path in sorted((REPO / folder).glob("*.py")):
            code = "\n".join(line for line in path.read_text().splitlines()
                             if not line.lstrip().startswith("#"))
            for m in re.finditer(r"\bdcc\.([A-Za-z]+)", code):
                if m.group(1) not in ALLOWED_DCC:
                    offenders.append(f"{folder}/{path.name}: dcc.{m.group(1)}")
    assert offenders == [], offenders


def test_the_traffic_page_uses_a_date_picker_not_a_dropdown():
    src = (REPO / "pages" / "traffic.py").read_text()
    assert "dcc.Dropdown" not in src
    assert "dmc.DatePickerInput" in src and 'valueFormat="YYYY-MM-DD"' in src
    assert "presets=" in src and "minDate=" in src and "maxDate=" in src


# --------------------------------------------------------- registry --


def test_other_apps_menu_is_the_registrys_primary_set(app_module):
    """Requirement 4 + the owner's review (2026-08-30): the PRIMARY
    applications only — never the docs subdomains — from the registry,
    no duplicates, self omitted, short labels (the domain)."""
    from components.header import create_other_apps_menu
    from lib.constants import BASE_URL
    from lib.network_directory import AFFILIATED, PEERS, PRIMARY, other_apps_for

    menu = create_other_apps_menu()
    items = menu.children[1].children
    hrefs = [i.href for i in items]
    expected = [e["url"] for e in other_apps_for(BASE_URL)]
    assert hrefs == expected
    assert set(h.rstrip("/") for h in hrefs) == PRIMARY - {BASE_URL.rstrip("/")}
    assert {"https://2plot.ai", "https://2plot.dev", "https://2plot.media",
            "https://piratesbargain.com", "https://ai-agent.buzz"} == set(PRIMARY)
    assert PRIMARY <= {e["url"].rstrip("/") for e in PEERS + AFFILIATED}, "PRIMARY names a URL the registry lacks"
    assert not any(".2plot.dev" in h for h in hrefs), "a docs subdomain leaked into the menu"
    assert len(set(hrefs)) == len(hrefs), "a host is listed twice"
    for item in items:
        label = item.children
        assert "." in label and " " not in label and "—" not in label, label
        assert item.target == "_blank"


def test_resources_are_third_party_only():
    """Owner's review (2026-08-30): the sidebar's Resources holds dmc and
    the upstream project only; the owner's own links are top bar + footer."""
    from lib.constants import DISCORD_URL, GITHUB_URL, YOUTUBE_URL, resources

    items = resources()
    assert items[0]["label"] == "dmc" and items[0]["url"] == "https://www.dash-mantine-components.com/"
    urls = [r["url"] for r in items]
    # NARROWED from the template's blanket "github.com" ban (filed upward
    # with this round's report): contract (5) requires the UPSTREAM project
    # link, and most of the fleet's upstreams — Excalidraw here, plus
    # FlexLayout, emoji-mart, model-viewer, Pannellum — have a GitHub repo
    # as their project home, so the blanket form makes the contract's own
    # requirement unsatisfiable. What the rule means is the OWNER's links,
    # which are the top bar's and the footer's; those are what is banned.
    from lib.constants import GITHUB_PROFILE_URL

    for banned in (GITHUB_URL, GITHUB_PROFILE_URL, DISCORD_URL, YOUTUBE_URL,
                   "pip-install-python", "discord", "youtube",
                   "community.plotly.com", "https://2plot.dev"):
        assert not any(banned in u for u in urls), banned


def test_github_icon_and_same_as_share_one_constant(app_module):
    from components.header import create_header
    from lib.constants import GITHUB_URL, SAME_AS

    assert GITHUB_URL in SAME_AS
    assert GITHUB_URL.startswith("https://github.com/pip-install-python/")
    assert GITHUB_URL.count("/") == 4, "the REPOSITORY, not the profile"
    assert GITHUB_URL in str(create_header([]))


# ---------------------------------------------------------- sidebar --


def test_sections_follow_category_order_and_never_hold_admin(app_module):
    import dash

    from components.navbar import sections_for
    from lib.constants import CATEGORY_ORDER

    data = list(dash.page_registry.values())
    sections = sections_for(data)
    titles = [t for t, _ in sections]
    known = [t for t in titles if t in CATEGORY_ORDER]
    assert known == [c for c in CATEGORY_ORDER if c in titles], titles
    for _, entries in sections:
        assert not any(e["path"].startswith("/admin/") for e in entries)
        assert not any(e["path"] in ("/", "/changelog", "/api") for e in entries)
    # the template's own docs all declare a category
    assert "Documentation" not in titles, "a docs page lost its category: frontmatter"


def test_frontmatter_order_sorts_within_a_section(app_module):
    import dash

    from components.navbar import sections_for

    for title, entries in sections_for(dash.page_registry.values()):
        orders = [int(e.get("order") or 1000) for e in entries]
        assert orders == sorted(orders), (title, orders)


def test_anonymous_tree_has_no_admin_href(app_module, monkeypatch):
    """Requirement 7: hidden, not blocked. The startup tree carries only an
    empty Admin placeholder; the callback returns nothing to a non-admin."""
    import dash

    from components.navbar import create_content, render_admin_section

    tree = str(create_content(dash.page_registry.values()))
    assert "/admin/" not in tree
    assert "navbar-admin-desktop" in tree
    monkeypatch.delenv("ALLOW_UNGATED_ADMIN", raising=False)
    assert render_admin_section("navbar-admin-desktop") == (None, None)


def test_admin_tree_lists_every_admin_page(app_module, monkeypatch):
    from components.navbar import render_admin_section

    monkeypatch.setenv("ALLOW_UNGATED_ADMIN", "1")
    desktop, mobile = render_admin_section("navbar-admin-desktop")
    text = str(desktop)
    assert "/admin/control-board" in text and "/admin/traffic" in text
    assert str(mobile) == text


def test_search_lists_only_sidebar_pages(app_module):
    import dash

    from components.navbar import search_data

    values = [d["value"] for d in search_data(dash.page_registry.values())]
    assert values and not any(v.startswith("/admin/") for v in values)
    assert "/" not in values and "/changelog" not in values


# ---------------------------------------------------------- footer --


def test_footer_is_the_contract(app_module):
    from datetime import datetime

    from components.footer import create_footer
    from lib.constants import DISCORD_URL, GITHUB_PROFILE_URL, GITHUB_URL, YOUTUBE_SUBSCRIBE_URL

    text = str(create_footer())
    assert f"© {datetime.now().year} Pip Install Python LLC" in text
    for href in (GITHUB_PROFILE_URL, DISCORD_URL, YOUTUBE_SUBSCRIBE_URL):
        assert href in text
    assert GITHUB_URL not in text, "the repo link is the top bar's; the footer links the profile"
    assert "/changelog" not in text, "the sidebar's single Changelog link is the one"
    assert "/terms" not in text and "/privacy" not in text


# ------------------------------------------------------- changelog --


def test_changelog_page_is_the_file(app_module, client):
    from pages.changelog import parse_changelog

    versions = parse_changelog()
    newest = re.search(r"^## \[([^\]]+)\]", (REPO / "CHANGELOG.md").read_text(), re.M).group(1)
    assert versions and versions[0]["version"] == newest
    doc = client.get("/changelog/llms.txt", user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert doc.status == 200
    assert doc.text.startswith("# Changelog") and "\n# Changelog" not in doc.text, "the file's H1 was not deduplicated"
    assert f"## [{newest}]" in doc.text
    page = client.get("/changelog", user_agent="Mozilla/5.0 (compatible; Googlebot/2.1)")
    assert page.status == 200 and newest in page.text


# ------------------------------------------------------------- api --


def test_api_reference_reads_a_dash_package_metadata():
    from lib import api_reference

    comps = api_reference.load_package("tests.fixtures.fake_dash_pkg")
    names = [c["name"] for c in comps]
    assert names == ["FakeGauge", "FakeWidget"], "sorted, exported only"
    widget = comps[1]
    props = {p["name"]: p for p in widget["props"]}
    assert "setProps" not in props
    assert props["value"]["required"] and props["value"]["default"] == "0"
    assert props["variant"]["type"].startswith("one of ")
    assert widget["props"][0]["name"] == "id"
    md = api_reference.as_markdown(["tests.fixtures.fake_dash_pkg"])
    assert "| `value` * | number | 0 | Current value. |" in md


def test_api_page_renders_one_table_per_component():
    from pages.api import build_page

    text = str(build_page(["tests.fixtures.fake_dash_pkg"]))
    assert "api-table-FakeWidget" in text and "api-table-FakeGauge" in text
    assert "Current value." in text


def test_the_api_page_is_registered_because_this_repo_ships_a_component(app_module):
    """INVERTED from the template's pin, deliberately. The template documents
    no component package and asserts /api is absent; this repo IS the
    component (divergence 1), so the page must exist and document it."""
    import dash

    from lib.constants import API_PACKAGES

    assert API_PACKAGES == ["dash_excalidraw"]
    assert "/api" in [p["path"] for p in dash.page_registry.values()]
    from lib import api_reference

    comps = api_reference.load_packages(API_PACKAGES)[0]
    assert not comps.get("error"), comps.get("error")
    assert [c["name"] for c in comps["components"]] == ["DashExcalidraw"]


def test_the_api_page_does_not_depend_on_a_gitignored_build_artifact():
    """The regression this test exists for, measured on run 33328319735.

    `dash_excalidraw/metadata.json` is a `dash-generate-components`
    byproduct: gitignored on purpose, and `scripts/check_release.py` asserts
    it is absent from the built wheel. So it exists ONLY on a machine that
    has run `npm run build` — never in a CI checkout, never in the
    production image. Reading it alone made /api document 38 props on the
    author's laptop and NOTHING anywhere else: green locally, red on all
    four pytest legs in CD, and an empty `## dash_excalidraw` section on the
    wire. The generated stub is tracked and IS in the wheel, so the
    docstring is the source that always exists.

    This pin reads the classes DIRECTLY, so it passes with or without the
    artifact present — which is the whole point.
    """
    import dash_excalidraw

    from lib import api_reference

    comps = api_reference._from_classes(dash_excalidraw)
    assert [c["name"] for c in comps] == ["DashExcalidraw"]
    props = {p["name"]: p for p in comps[0]["props"]}
    assert len(props) >= 30, sorted(props)
    assert props["id"]["type"] == "string"
    assert "setProps" not in props
    assert comps[0]["props"][0]["name"] == "id", "id sorts first"
    assert props["command"]["description"], "descriptions survived the parse"


def test_missing_package_is_reported_not_raised():
    from lib import api_reference

    out = api_reference.load_packages(["no_such_dash_package_xyz"])
    assert out[0]["components"] == [] and "error" in out[0]


# ------------------------------------------------ 1.6.39 fix-forward --


def test_the_aside_collapses_on_pages_without_a_toc(app_module):
    """Owner's note 1: /changelog full width. Docs pages with `.. toc::`
    keep the column; everything else collapses it."""
    from lib.aside import aside_config, has_aside

    assert has_aside("/basic") and has_aside("/events")
    for path in ("/changelog", "/", "/admin/traffic", "/api"):
        assert not has_aside(path), path
        assert aside_config(path)["collapsed"]["desktop"] is True
    assert aside_config("/basic")["collapsed"]["desktop"] is False
    assert aside_config(None)["collapsed"]["mobile"] is True


def test_the_mobile_drawer_is_always_mounted(app_module):
    """Owner's note 2: the burger must not depend on a mount-on-open
    transition, and #navbar-admin-mobile must exist on every load."""
    from components.navbar import create_navbar_drawer

    drawer = create_navbar_drawer([])
    assert drawer.keepMounted is True
    assert "navbar-admin-mobile" in str(drawer)


def test_code_blocks_cannot_widen_the_page():
    """Owner's note 3: the overflow rule lives in the stylesheet, for every
    container a code block can sit in — never a per-page fix."""
    css = (REPO / "assets" / "main.css").read_text()
    for selector in (".mantine-List-itemWrapper", ".mantine-List-itemLabel",
                     ".mantine-Timeline-itemBody", ".mantine-CodeHighlight-root",
                     ".mantine-CodeHighlightTabs-root", ".mantine-AppShell-main pre",
                     "table.m2d-block-kwargs", "code.m2d-codespan"):
        assert selector in css, selector
    # and the changelog's rows let an unbreakable code token wrap
    src = (REPO / "pages" / "changelog.py").read_text()
    assert '"overflowWrap": "anywhere"' in src and '"minWidth": 0' in src
    wrappers = css[css.index(".mantine-List-itemWrapper"):]
    assert "min-width: 0" in wrappers[:400]
    pre_rule = css[css.index(".mantine-AppShell-main pre"):]
    assert "overflow-x: auto" in pre_rule[:200]
    assert "overflow-wrap: anywhere" in css[css.index("code.m2d-codespan"):][:200]


def test_other_apps_dropdown_is_solid_and_every_primary_app_has_an_icon(app_module):
    """Seat's note 4."""
    from components.header import create_other_apps_menu
    from lib.network_directory import ICONS, PRIMARY

    dropdown = create_other_apps_menu().children[1]
    assert dropdown.styles["dropdown"]["backgroundColor"]
    for url in PRIMARY:
        assert ICONS.get(url) not in (None, "mdi:web"), f"{url} has no icon"
