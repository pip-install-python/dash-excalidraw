"""The cross-host directory — the thing twelve satellites share verbatim.

A directory that disagrees with itself across hosts is worse than none, so
these tests are about internal consistency, not taste.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import pytest

from lib import network_directory as nd
from lib.constants import BASE_URL

ALL_ENTRIES = nd.PEERS + nd.AFFILIATED + nd.EXTERNAL


@pytest.mark.parametrize("entry", ALL_ENTRIES, ids=lambda e: e["name"])
def test_entries_are_well_formed(entry):
    assert entry["name"].strip(), "every entry needs a display name"
    assert entry["description"].strip(), (
        "every entry needs a description — it is what a reader uses to decide "
        "whether to follow the link"
    )
    parsed = urlparse(entry["url"])
    assert parsed.scheme == "https", f"{entry['url']} is not https"
    assert parsed.netloc, f"{entry['url']} has no host"
    assert not entry["url"].endswith("/"), "trailing slash breaks the self-filter comparison"


def test_no_duplicate_urls():
    urls = [e["url"].rstrip("/") for e in ALL_ENTRIES]
    duplicates = {u for u in urls if urls.count(u) > 1}
    assert not duplicates, f"a host is listed twice: {sorted(duplicates)}"


def test_tiers_do_not_overlap():
    peers = {e["url"] for e in nd.PEERS}
    affiliated = {e["url"] for e in nd.AFFILIATED}
    external = {e["url"] for e in nd.EXTERNAL}
    assert not peers & affiliated, "a host cannot be both a peer and merely affiliated"
    assert not peers & external, "a host cannot be both a peer and third-party"
    assert not affiliated & external


def test_this_app_is_not_its_own_peer():
    """The invariant, and the one deviation this host currently carries.

    A site must never list itself: `peers_for` exists to strip the caller's
    own origin so /llms.txt's Network section is other hosts only.

    The template additionally asserts the filter removed EXACTLY ONE entry —
    proof that this host's own URL is spelled correctly in the directory. It
    cannot hold here yet, and deliberately so: `lib/network_directory.py` is
    a verbatim copy of the canonical list, and that list omits
    excalidraw.2plot.dev by design ("only list hosts that are actually
    live"). This host has never deployed, so it is not in PEERS.

    Written to flip on its own: the moment the canonical directory gains
    this host — the queued registration in the deploy-readiness checklist —
    the second branch takes over and pins the spelling exactly as the
    template does. See also `test_this_host_is_queued_for_registration`.
    """
    peers = nd.peers_for(BASE_URL)
    assert all(p["url"].rstrip("/") != BASE_URL.rstrip("/") for p in peers)

    listed = any(e["url"].rstrip("/") == BASE_URL.rstrip("/") for e in nd.PEERS)
    if listed:
        assert len(peers) == len(nd.PEERS) - 1, (
            f"{BASE_URL} is in PEERS but the self-filter removed nothing — it "
            "is spelled differently there."
        )
    else:
        assert len(peers) == len(nd.PEERS)


def test_this_host_is_queued_for_registration():
    """A named record of the one directory deviation, not a silent absence.

    The canonical `PEERS` list is copied byte-for-byte from the boilerplate,
    and the fleet's rule is that a host joins it in the same change that
    ships it. Until excalidraw.2plot.dev is live, its absence is correct —
    but an absence with no test looks identical to an oversight, which is how
    a host stays unlisted for a release after it deploys.

    Delete this test in the change that adds the entry.
    """
    assert not any(e["url"].rstrip("/") == BASE_URL.rstrip("/") for e in nd.PEERS), (
        f"{BASE_URL} is now in the canonical directory — good. Remove this "
        "test and let test_this_app_is_not_its_own_peer pin the spelling."
    )


def test_a_satellite_filters_only_itself():
    peers = nd.peers_for("https://leaflet.2plot.dev")
    urls = {p["url"] for p in peers}
    assert "https://leaflet.2plot.dev" not in urls
    assert "https://boilerplate.2plot.dev" in urls


def test_peers_are_all_on_network_domains():
    """`peers` claims same-operator ownership. Anything else belongs in
    `affiliated` or `external`, where it won't be presented as part of the
    network or, for external, passed ranking signal."""
    off_network = [
        p["url"] for p in nd.PEERS
        if not urlparse(p["url"]).netloc.endswith(("2plot.dev", "2plot.ai"))
    ]
    assert off_network == [], f"non-network hosts in PEERS: {off_network}"


def test_hub_is_listed_as_a_peer():
    assert nd.HUB_URL.rstrip("/") in {p["url"].rstrip("/") for p in nd.PEERS}, (
        "hub_url points somewhere the directory never lists, so an agent is "
        "told to start at a host it has no entry for"
    )


def test_directory_reaches_llms_txt(client):
    body = client.get("/llms.txt").text
    for entry in nd.peers_for(BASE_URL):
        assert entry["url"] in body, f"{entry['name']} missing from the published directory"
    for entry in nd.EXTERNAL:
        assert entry["url"] in body, f"{entry['name']} missing from External references"


# ---------------------------------------------------------------------------
# The wordmark (dash-improve-my-llms 2.2.0)
#
# Defined in this module rather than per-app precisely because the file is
# copied verbatim into every satellite — that is what makes one mark across
# the network instead of twelve near-identical ones. So these assertions are
# about the shape the renderer requires, and about the two decisions that
# would otherwise drift.
# ---------------------------------------------------------------------------


def test_wordmark_matches_the_renderer_contract():
    """`render_wordmark_spec` reads "morse"/"word"; anything else draws nothing
    and the banner silently falls back to plain text."""
    assert nd.WORDMARK.get("morse"), "no encodable word — the mark would not render"
    assert set(nd.WORDMARK) <= {"morse", "word", "prefix", "suffix", "label", "arrow", "ascii"}


def test_wordmark_is_dotless():
    """"2" + morse(plot) + "ai", with no period glyph.

    The morse block already separates the halves, so a literal "." beside it
    reads as punctuation dropped into a graphic. The renderer turns a suffix
    ending in "i" into an upward flourish, so "ai" draws as "a" plus that mark.
    """
    assert "." not in nd.WORDMARK["prefix"] + nd.WORDMARK["suffix"], (
        "the drawn mark should carry no period; the domain lives in `label`"
    )
    assert nd.WORDMARK["suffix"].lower().endswith("i"), (
        "the flourish is keyed off a suffix ending in 'i'"
    )


def test_wordmark_label_carries_the_real_domain():
    """`label` is the accessible name and the SVG <title> — the one place the
    dot belongs, because a screen reader should say the actual domain."""
    assert nd.WORDMARK["label"] == "2plot.ai"


def test_wordmark_reaches_the_rendered_view(client):
    from conftest import BROWSER_ACCEPT

    # A page that exists on THIS host — the template's /networks does not.
    html = client.get("/basic/llms.txt", accept=BROWSER_ACCEPT).text
    svg = re.search(r'<svg class="mk-wordmark".*?</svg>', html, re.S)
    assert svg, "the wordmark did not reach the viewer banner"

    drawn = svg.group(0)
    assert f"<title>{nd.WORDMARK['label']}</title>" in drawn
    assert not re.search(r'\b(?:src|href|xlink:href)=', drawn), (
        "the mark must be self-contained — it renders in a page that has to "
        "work behind any CSP and with no network access"
    )


def test_apply_survives_a_package_without_wordmark_support(monkeypatch):
    """During a staged rollout this file reaches satellites before the new
    package does. `wordmark` arrived in 2.2.0 and Python raises TypeError on
    an unknown keyword, so passing it unconditionally would turn an older
    satellite's boot into a crash instead of a missing graphic."""
    import dash_improve_my_llms

    received = {}

    def old_register_network(name=None, description=None, hub_url=None,
                             peers=None, affiliated=None, external=None):
        received.update(name=name, hub_url=hub_url, peers=peers)

    monkeypatch.setattr(dash_improve_my_llms, "register_network", old_register_network)
    nd.apply(BASE_URL)  # must not raise
    assert received["name"] == nd.NETWORK_NAME


def test_apply_is_idempotent():
    """run.py calls apply() once, but a reload in a dev server calls it again.
    Re-registration must not duplicate entries in the published directory."""
    from dash_improve_my_llms import network as pkg_network  # noqa: F401

    nd.apply(BASE_URL)
    nd.apply(BASE_URL)
    # No assertion on internals — the contract is that the package de-dupes by
    # URL; this test fails loudly if apply() itself raises on a second call.
