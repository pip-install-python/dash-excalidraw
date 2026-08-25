"""The interactive gate's presentation layer (lib/gate_layouts.py).

The verdict logic is tested in test_access.py; here the contract is the
wrapper itself: the right card per verdict, content only on allow, the
**kwargs tolerance Dash Pages requires, and the funnel surviving a broken
teaser demo.
"""

from __future__ import annotations

import pytest

from lib import access, gate_layouts


def _ids(component, found=None):
    """Every component id in a Dash tree."""
    found = found if found is not None else set()
    comp_id = getattr(component, "id", None)
    if isinstance(comp_id, str):
        found.add(comp_id)
    children = getattr(component, "children", None)
    if isinstance(children, (list, tuple)):
        for child in children:
            _ids(child, found)
    elif children is not None:
        _ids(children, found)
    return found


CONTENT = "the real page content"


@pytest.fixture
def wrapped(app_module):
    return gate_layouts.gated_layout("/some-page", "Some Page", CONTENT)


def test_allow_returns_the_content(wrapped, monkeypatch):
    monkeypatch.setattr(access, "resolve_page_access", lambda p: "allow")
    assert wrapped() == CONTENT


def test_allow_calls_a_callable_layout(app_module, monkeypatch):
    monkeypatch.setattr(access, "resolve_page_access", lambda p: "allow")
    layout = gate_layouts.gated_layout("/p", "P", lambda: CONTENT)
    assert layout() == CONTENT


def test_sign_in_renders_the_funnel_card_with_both_buttons(wrapped, monkeypatch):
    monkeypatch.setattr(access, "resolve_page_access", lambda p: "sign_in")
    card = wrapped()
    ids = _ids(card)
    assert "auth-gate-signup" in ids and "auth-gate-signin" in ids
    assert CONTENT not in str(card)


def test_forbidden_and_hidden_render_cards_not_content(wrapped, monkeypatch):
    for verdict in ("forbidden", "hidden"):
        monkeypatch.setattr(access, "resolve_page_access", lambda p: verdict)
        assert CONTENT not in str(wrapped())


def test_the_layout_accepts_dash_pages_kwargs(wrapped, monkeypatch):
    """Dash Pages forwards query params (incl. Clerk's ?__clerk_handshake=)
    into layout callables — the wrapper must swallow them."""
    monkeypatch.setattr(access, "resolve_page_access", lambda p: "allow")
    assert wrapped(__clerk_handshake="abc", utm_source="x") == CONTENT


def test_the_verdict_runs_per_render_not_per_registration(wrapped, monkeypatch):
    """An env flip applies on the next navigation — nothing is baked in."""
    monkeypatch.setattr(access, "resolve_page_access", lambda p: "sign_in")
    assert CONTENT not in str(wrapped())
    monkeypatch.setattr(access, "resolve_page_access", lambda p: "allow")
    assert wrapped() == CONTENT


def test_a_broken_demo_never_breaks_the_funnel(app_module, monkeypatch):
    """lib/auth_demos degrades to the demo-less card on any failure, and the
    card itself tolerates build_demo raising — a broken example must never
    take down the sign-in funnel."""
    from lib import auth_demos

    monkeypatch.setitem(
        auth_demos.DEMOS, "/broken",
        {"module": "docs.does_not_exist.nope", "caption": "x"},
    )
    assert auth_demos.build_demo("/broken") is None

    def boom(path):
        raise RuntimeError("demo table bug")

    monkeypatch.setattr(auth_demos, "build_demo", boom)
    card = gate_layouts.sign_in_layout("Page", "/broken")
    assert "auth-gate-signup" in _ids(card)


def test_the_gate_card_names_the_sign_in_destination(app_module, monkeypatch):
    """No hardcoded URLs: the destination comes from access.sign_in_url()
    (bulletin first, env second), falling back to the network primary."""
    monkeypatch.setattr(access, "sign_in_url", lambda: "https://example.test/in")
    assert "https://example.test/in" in str(gate_layouts.sign_in_layout("P"))
    monkeypatch.setattr(access, "sign_in_url", lambda: None)
    assert "https://2plot.ai" in str(gate_layouts.sign_in_layout("P"))


def test_every_registered_teaser_demo_actually_resolves(app_module):
    """The template's demo table is fork cargo, and it fails SILENTLY.

    `build_demo` swallows every import error by design (a broken example must
    not take down the funnel), and the warning it logs only fires when the
    card for that endpoint renders — which never happens if the endpoint is
    not a page here. This fork shipped the template's
    /examples/visualization -> docs.data-visualization.basic_chart entry from
    fork time until 2026-08-25: no page, no module, no warning, and every
    gate card on the site quietly rendering the demo-less variant.

    So pin both halves: the endpoint is a real page, and the module imports
    and exposes `component`.
    """
    import importlib

    from dash import page_registry

    from lib import auth_demos

    endpoints = {page["path"] for page in page_registry.values()}
    for path, spec in auth_demos.DEMOS.items():
        assert path in endpoints, (
            f"auth-gate demo registered for {path!r}, which is not a page on "
            f"this site — the card can never render it. Known: {sorted(endpoints)}"
        )
        module = importlib.import_module(spec["module"])
        assert hasattr(module, "component"), (
            f"{spec['module']} has no module-level `component` — build_demo "
            "returns None and the teaser is dead"
        )


def test_the_gate_card_promises_only_what_this_site_ships(app_module):
    """SYNC-1.6.10-1.6.16 item 9, ported as its CONTRACT rather than its fix.

    The template retired "and the AI assistant" from the demo-branch intro
    because no fork wired one, and a gate card selling a feature that does
    not exist spends the network's credibility at its highest-intent moment.
    THIS fork wires one: docs/ai-agent (`endpoint: /ai-agent`) is a real page
    and its frontmatter says `tier: auth`, so an account genuinely unlocks
    it. The copy stays, and this pin is what keeps it earned — delete the
    page, or open its tier, and the promise becomes a lie with a red test
    attached. Recorded in DIVERGENCES.md.
    """
    import re
    from pathlib import Path

    import frontmatter

    source = (Path(__file__).resolve().parent.parent / "lib" / "gate_layouts.py").read_text()
    # Comments stripped first: the template's own fix names the phrase it
    # retired IN a comment, so a raw grep answers wrong in both directions
    # (emojimart's spec correction, 2026-08-24).
    code = re.sub(r"^\s*#.*$", "", source, flags=re.M)
    if "the AI assistant" not in code:
        return  # the template's string; nothing to earn

    gated = {
        post.metadata.get("endpoint"): post.metadata.get("tier")
        for md in (Path(__file__).resolve().parent.parent / "docs").glob("*/*.md")
        for post in [frontmatter.loads(md.read_text())]
    }
    assert gated.get("/ai-agent") == "auth", (
        "lib/gate_layouts.py promises 'the AI assistant' behind the sign-in "
        "gate, but docs/ai-agent is not `tier: auth` on this site "
        f"(tier={gated.get('/ai-agent')!r}). Either gate the page or retire "
        "the phrase, as the template did."
    )
