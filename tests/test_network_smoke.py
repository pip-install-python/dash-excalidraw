"""Run the network battery against the in-process app.

`scripts/network_smoke.py` only ever executes in two places a developer never
watches: against the container CI just booted, and against production after a
deploy. That is exactly the code that rots — a typo in a check turns it into a
silent pass and the battery keeps reporting green over a broken host.

So it runs here too, with its `fetch` pointed at the test client. Three
distinct things get proven, and it is worth being explicit about which:

1. the battery's own logic still works (the checks fire, and they can fail);
2. this app satisfies every check the network standard makes of a satellite;
3. the per-site block at the top of the script — the expected H1, the hidden
   paths — still matches the app it describes.

What it cannot prove is the deployed artifact, which is the whole reason the
container run and the post-deploy run exist as well.
"""

from __future__ import annotations

import re

import importlib.util
import sys

import pytest

from conftest import REPO_ROOT
from lib.constants import BASE_URL, INTERNAL_UA_TOKEN, SITE_BRAND

BASE = BASE_URL


@pytest.fixture(scope="module")
def battery():
    spec = importlib.util.spec_from_file_location(
        "network_smoke", REPO_ROOT / "scripts" / "network_smoke.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["network_smoke"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def wired(battery, client, monkeypatch):
    """Point the battery's `fetch` at the test client.

    The signature is `fetch(url, ua=..., method=..., body=..., headers=...)`
    and it returns `(status, lowercased_headers, text)`. Only GET is used by
    the satellite battery, so a non-GET here is a bug in the script rather
    than something to emulate.
    """
    seen_agents = []

    def fetch(url, ua=battery.UA, method="GET", body=None, headers=None,
              timeout=None, retries=1):
        assert method == "GET", f"the satellite battery issued a {method}"
        seen_agents.append(ua)
        path = url[len(BASE):] if url.startswith(BASE) else url
        accept = (headers or {}).get("Accept")
        response = client.get(path or "/", user_agent=ua, accept=accept)
        return response.status, dict(response.headers), response.text

    monkeypatch.setattr(battery, "fetch", fetch)
    monkeypatch.setattr(battery, "_RESULTS", [])
    # No declaration in the in-process seat: here the "host" serves from the
    # suite's own interpreter, which on the matrix's window legs (3.13/3.12)
    # is deliberately not the fleet Python. The python_matches_declared
    # check still proves the field EXISTS; holding the artifact to the
    # Dockerfile's minor is the container and production seats' job, and
    # ci.yml's gunicorn boot step stands the check down the same way with
    # SMOKE_PYTHON_DECLARED=ignore.
    monkeypatch.setattr(battery, "declared_python_minor", lambda: None)
    battery.seen_agents = seen_agents
    return battery


def test_the_battery_passes_against_this_app(wired, capsys):
    wired.satellite_checks(BASE)
    output = capsys.readouterr().out

    failed = [(name, detail) for name, verdict, detail in wired._RESULTS
              if verdict == wired.FAIL]
    assert failed == [], f"battery failures against the in-process app:\n{output}"
    assert len(wired._RESULTS) >= 9, "checks silently stopped running"


def test_every_request_the_battery_makes_is_internal(wired):
    """A battery that pollutes the ledger it is auditing is worse than none."""
    wired.satellite_checks(BASE)
    untokened = [ua for ua in wired.seen_agents if INTERNAL_UA_TOKEN not in ua]
    assert untokened == [], f"battery sent untokened User-Agents: {untokened}"


def test_the_expected_h1_tracks_the_brand_constant(battery):
    """The per-site block is a copy of `SITE_BRAND`; copies drift."""
    assert battery.SITE_H1 == f"# {SITE_BRAND}"


def test_the_battery_reports_a_failure_rather_than_swallowing_it(wired):
    """The check that keeps every other assertion here honest.

    If `check()` ever caught too broadly, the battery would print `pass` for a
    host that is on fire. Break one expectation on purpose and require it to
    be reported.
    """
    wired.SITE_H1 = "# not this site"
    try:
        wired.satellite_checks(BASE)
    finally:
        wired.SITE_H1 = f"# {SITE_BRAND}"

    verdicts = {name: verdict for name, verdict, _ in wired._RESULTS}
    assert verdicts.get("llms_txt_identity") == wired.FAIL


def test_the_default_base_url_matches_the_container_port(battery):
    """CI boots the image and runs the battery with no --base-url.

    The CMD no longer hardcodes a port — it binds ``$PORT``, because Render
    assigns one and a container that ignores it is unreachable. So the
    invariant moved rather than disappeared: what must agree is the battery's
    default, ``EXPOSE``, and the ``PORT`` default the image ships. Asserted as
    three separate facts, since a mismatch in any one of them is a container
    CI boots and then cannot reach.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()
    port = battery.DEFAULT_BASE_URL.rsplit(":", 1)[1]
    assert f"EXPOSE {port}" in dockerfile, (
        f"the battery defaults to port {port}; the image exposes something else"
    )
    assert re.search(rf"^\s*PORT={port}\s*$", dockerfile, re.M), (
        f"the image's PORT default is not {port}, so a `docker run` with no "
        "-e PORT listens somewhere the battery does not look"
    )
    assert f'--bind "0.0.0.0:${{PORT:-{port}}}"' in dockerfile, (
        f"the CMD must bind ${{PORT:-{port}}} — Render assigns the port at "
        "runtime and a container listening on a hardcoded one never passes "
        "its health check, while a BARE ${PORT} collapses the bind to "
        '"0.0.0.0:" the moment the platform sets the variable to empty. The '
        "ENV default above covers unset, not set-empty, so the number is "
        "repeated at the point of use (SYNC-1.6.10-1.6.16 item 5)."
    )
    assert f'localhost:${{PORT:-{port}}}/healthz' in dockerfile, (
        f"the HEALTHCHECK must probe ${{PORT:-{port}}} — the same variable "
        "with the same default as the bind, or it checks a port nothing is "
        "listening on and reports an unhealthy container that is fine"
    )


def test_every_network_smoke_urlopen_passes_the_ssl_context():
    """Source pin: EVERY urlopen in network_smoke.py carries
    context=SSL_CONTEXT.

    The sibling of tests/test_smoke_live.py's pin, and added for a defect
    measured on this seat: stdlib on macOS ships no OS trust-store
    integration, so a naked urlopen dies in the TLS handshake, burns all
    three retry attempts on it, and the battery reports a healthy production
    host as DOWN. CI cannot see it (Linux verifies fine) and no wired test
    can (they monkeypatch `fetch`), so a SOURCE pin is the only net with a
    mesh this fine.

    This is one of the two places the fleet's battery reads a live host, and
    it was the one still naked — the template's own copy at 1.6.29 has the
    same gap, filed upward with this round's report.
    """
    source = (REPO_ROOT / "scripts" / "network_smoke.py").read_text()
    calls = re.findall(r"urlopen\((?:[^)]|\n)*?\)", source)
    assert calls, "no urlopen calls found in network_smoke.py — probe rewritten?"
    naked = [c for c in calls if "context=SSL_CONTEXT" not in c]
    assert not naked, (
        f"urlopen without context=SSL_CONTEXT in network_smoke.py: {naked} — "
        "on macOS this dies in the handshake and reads as a host that is down"
    )
