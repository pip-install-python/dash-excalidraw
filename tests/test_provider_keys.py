"""Every provider key is blanked before the suite can spend money.

THE HOLE THIS CLOSES, measured at 46a1694: `tests/conftest.py` blanked a
hand-kept `SECRET_ENV_KEYS` tuple that named Clerk, the session secrets and
the databases — and not one provider key. `CHATGPT_API_KEY` reached
`lib/scene_ai.py` in E2 and never reached that tuple. On any machine holding
that key in its shell or `.env`, `available_models` would have called the live
endpoint on every run. It is a GET, so nothing would have been billed; the
POST that costs money sits behind the same absent fence.

So the fence is no longer hand-kept. conftest imports the names from the
module that reads them, and the test below asserts the two agree — which is
what makes forgetting the NEXT provider a red test rather than a live call.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from lib.scene_ai import PROVIDER_KEY_VARS

MODULE = Path(__file__).resolve().parent.parent / "lib" / "scene_ai.py"

# `os.environ.get("NAME")` / `os.environ["NAME"]` for anything that looks like
# a credential. Deliberately not every env read — RENDER and APP_ENV are
# posture flags, not keys, and blanking them would change what is tested.
_READS = re.compile(r"""os\.environ(?:\.get)?[(\[]\s*["']([A-Z0-9_]+)["']""")
_CREDENTIAL = re.compile(r"(_KEY|_TOKEN|_SECRET)$")


def _keys_the_module_reads() -> set[str]:
    src = MODULE.read_text(encoding="utf-8")
    return {n for n in _READS.findall(src) if _CREDENTIAL.search(n)}


class TestTheFenceIsDerivedNotHandKept:
    def test_the_module_reads_at_least_one_key(self):
        # Non-vacuity. If the regex stopped matching, every assertion below
        # would pass against an empty set and the fence would be gone.
        found = _keys_the_module_reads()
        assert found, "no credential env reads found — the detector is broken"

    def test_every_key_the_module_reads_is_declared(self):
        undeclared = _keys_the_module_reads() - set(PROVIDER_KEY_VARS)
        assert not undeclared, (
            f"lib/scene_ai.py reads {sorted(undeclared)} but PROVIDER_KEY_VARS "
            f"does not declare them, so conftest never blanks them and the "
            f"suite can reach a live provider."
        )

    def test_the_declared_extras_are_deliberate(self):
        # PROVIDER_KEY_VARS may legitimately be a SUPERSET: the Anthropic SDK
        # reads ANTHROPIC_AUTH_TOKEN itself, without this module ever naming
        # it, and blanking only ANTHROPIC_API_KEY would still leave a
        # configured client. Anything else extra is a stale entry.
        extra = set(PROVIDER_KEY_VARS) - _keys_the_module_reads()
        assert extra <= {"ANTHROPIC_AUTH_TOKEN"}, (
            f"PROVIDER_KEY_VARS declares {sorted(extra)} which nothing reads"
        )


class TestTheyAreActuallyBlankDuringTheSuite:
    """The list being right is worthless if conftest does not apply it."""

    @pytest.mark.parametrize("name", PROVIDER_KEY_VARS)
    def test_each_one_is_falsy(self, name):
        # "" not absent: `load_dotenv()` never overrides an existing key, so
        # pinning to empty neutralises a developer's .env without deleting it.
        assert not os.environ.get(name), (
            f"{name} is set during the test suite — a real provider call is "
            f"one code path away"
        )

    def test_a_configured_client_cannot_be_built(self):
        # The end the fence exists for, asserted directly rather than inferred
        # from the variables: the availability check must report "unknown"
        # instead of reaching the network.
        from lib import scene_ai

        scene_ai._AVAILABILITY_CACHE.clear()
        try:
            assert scene_ai._reported_claude_models() is None
        finally:
            scene_ai._AVAILABILITY_CACHE.clear()


class TestTheKeylessPosture:
    """The deployed site holds NO provider keys, permanently.

    Decided 2026-09-12: excalidraw.2plot.dev is documentation and will not
    spend tokens on demos. So "no keys" is not an error path taken by
    accident — it is the production state of three pages, and it has to render
    as a deliberate posture rather than as a fault.

    MEASURED before this was fixed, in a keyless process: /ai-agent showed
    three RED badges and an enabled Generate button that answered a click with
    a red error; /trace-image the same; and /benchmark had NO key check at all
    — it started every variant, turned the ticker on, and let each cell fail
    separately from its worker. A spinner followed by six red panels, on a
    site that is never going to have keys. Any reader would file that as a bug.
    """

    PAGES = (
        ("docs/ai-agent/ai_agent.py", "ai_agent"),
        ("docs/benchmark/benchmark.py", "benchmark"),
        ("docs/trace-image/trace_image.py", "trace_image"),
    )

    def _load(self, rel, name, monkeypatch, keys: dict):
        import importlib.util
        import sys

        from lib.scene_ai import PROVIDER_KEY_VARS

        for var in PROVIDER_KEY_VARS:
            monkeypatch.delenv(var, raising=False)
        for var, value in keys.items():
            monkeypatch.setenv(var, value)

        path = Path(__file__).resolve().parent.parent / rel
        spec = importlib.util.spec_from_file_location(f"posture_{name}", path)
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, f"posture_{name}", module)
        spec.loader.exec_module(module)
        return module

    @pytest.mark.parametrize("rel,name", PAGES, ids=[n for _, n in PAGES])
    def test_without_keys_the_run_control_is_off(self, rel, name, monkeypatch):
        page = self._load(rel, name, monkeypatch, {})
        assert page.ANY_KEY is False
        # Index 1 is the run/generate button's `disabled` on all three pages.
        # `_lock_controls` fires on first render, so a page that disabled the
        # button only in the layout would have it switched back on immediately.
        assert page._lock_controls(True)[1] is True, (
            "the run control was re-enabled on first render, offering a click "
            "whose only possible outcome is an error"
        )

    @pytest.mark.parametrize("rel,name", PAGES, ids=[n for _, n in PAGES])
    def test_with_a_key_the_run_control_works(self, rel, name, monkeypatch):
        # Non-vacuity: the test above must not pass because the button is
        # always disabled. Locally, with a `.env`, these pages work.
        page = self._load(rel, name, monkeypatch, {"ANTHROPIC_API_KEY": "sk-local"})
        assert page.ANY_KEY is True
        assert page._lock_controls(True)[1] is False

    def test_ai_agent_shows_one_calm_notice_not_red_badges(self, monkeypatch):
        page = self._load(*self.PAGES[0], monkeypatch=monkeypatch, keys={})
        rendered = str(page._provider_status())
        assert "disabled on this site" in rendered
        assert "'red'" not in rendered, (
            "red reads as a fault; nothing is broken and nothing the reader "
            "can do would fix it"
        )

    def test_benchmark_starts_nothing_without_keys(self, monkeypatch):
        page = self._load(*self.PAGES[1], monkeypatch=monkeypatch, keys={})
        started = []
        monkeypatch.setattr(
            page.scene_stream, "start", lambda **kw: started.append(kw) or "rid"
        )
        _cells, tick_disabled, message, colour, *_ = page._run(
            1, "claude-opus-5", "effort", ["low", "high"], None, None,
            24000, "low", "draw a cat",
        )
        assert started == [], "a keyless sweep started runs that could only fail"
        assert tick_disabled is True, "the ticker span up with nothing to collect"
        assert colour == "blue"
        assert "without provider keys" in str(message)

    @pytest.mark.parametrize("rel,name", PAGES, ids=[n for _, n in PAGES])
    def test_a_forced_request_is_answered_calmly(self, rel, name, monkeypatch):
        # The buttons are disabled, so reaching the callback takes a crafted
        # request. That is still not the caller's fault, so it gets the same
        # words and the same colour as the notice.
        page = self._load(rel, name, monkeypatch, {})
        if name == "ai_agent":
            out = page._generate(1, "claude", "claude-opus-5", "low", 24000, "x")
            message, colour = out[1], out[2]
        elif name == "benchmark":
            out = page._run(1, "claude-opus-5", "effort", ["low"], None, None,
                            24000, "low", "x")
            message, colour = out[2], out[3]
        else:
            img = {"media_type": "image/png", "b64": "AAA", "width": 10,
                   "height": 10, "data_url": "data:,"}
            out = page._trace(1, "claude-opus-5", "low", 24000, "", img)
            message, colour = out[2], out[3]
        assert colour == "blue", f"{name} answered with a {colour} error"
        assert "without provider keys" in str(message)


class TestTheDocsSaySo:
    """So a reader does not file "the AI page is broken"."""

    @pytest.mark.parametrize(
        "doc",
        ["docs/ai-agent/ai-agent.md", "docs/benchmark/benchmark.md",
         "docs/trace-image/trace-image.md"],
    )
    def test_each_page_explains_the_keyless_site(self, doc):
        text = (Path(__file__).resolve().parent.parent / doc).read_text(encoding="utf-8")
        assert "no provider keys" in text
        assert "locally" in text
        assert "not a fault" in text
