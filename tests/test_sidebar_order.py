"""This site's sidebar, in the order the owner chose (2026-09-22).

tests/test_nav_contract.py proves the sidebar FOLLOWS `CATEGORY_ORDER`, and
that pages sort by `order:` inside a section. Neither says what the order IS,
and neither notices two pages sharing an `order:` — which is how Coverage sat
between Benchmark and Trace an image, sorted there by name alone.
"""

from __future__ import annotations


def _sections():
    import dash

    from components.navbar import sections_for

    return sections_for(dash.page_registry.values())


def test_sections_read_getting_started_appearance_data_flow_advanced(app_module):
    titles = [title for title, _ in _sections()]
    assert titles == ["Getting started", "Appearance", "Data flow", "Advanced"], titles


def test_no_two_pages_in_a_section_share_an_order(app_module):
    sections = _sections()
    assert sum(len(entries) for _, entries in sections) >= 15, "corpus too small"
    for title, entries in sections:
        orders = [int(e.get("order") or 1000) for e in entries]
        assert len(orders) == len(set(orders)), (title, orders)


def test_scene_viewer_sits_right_after_trace_an_image(app_module):
    advanced = dict(_sections())["Advanced"]
    paths = [e["path"] for e in advanced]
    assert paths.index("/scene-viewer") == paths.index("/trace-image") + 1, paths
    assert paths[-1] == "/coverage", paths


def test_the_mobile_drawer_closes_when_the_page_changes(app_module):
    """DIVERGENCES.md 18. Drawer links route client-side, so without this the
    drawer stays open over the page the reader just picked (measured)."""
    import dash._callback as registry

    # Both places: Dash's first server setup MOVES the global list into the
    # app and clears it, so which one holds the callbacks depends on whether
    # an earlier test in the session made a request.
    app = app_module.app
    callbacks = list(registry.GLOBAL_CALLBACK_LIST) + list(app._callback_list)
    scripts = list(registry.GLOBAL_INLINE_SCRIPTS) + list(app._inline_scripts)
    drawer = [c for c in callbacks
              if c["output"].split("@")[0] == "components-navbar-drawer.opened"]
    assert drawer, "no callback drives the drawer at all — the check would be vacuous"
    closers = [c for c in drawer
               if {"id": "url", "property": "pathname"} in c["inputs"]]
    assert len(closers) == 1, [c["inputs"] for c in drawer]
    name = closers[0]["clientside_function"]["function_name"]
    source = next(s for s in scripts if name in s)
    assert "return false" in source
