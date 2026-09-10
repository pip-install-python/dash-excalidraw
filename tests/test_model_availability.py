"""The offered model list, checked against what the key can actually call.

The static tables in `lib/scene_ai` say what this site knows how to price and
drive. They say nothing about what a given API key is entitled to call, and
offering a model the key cannot use turns a click into a provider error the
page cannot explain.

THE CASE THAT DECIDED THE DESIGN, measured 2026-09-10 against this
deployment's own key: `GET /v1/models` lists ``claude-haiku-4-5-20251001``,
while the table — and every working call this site has ever made — uses the
alias ``claude-haiku-4-5``. A literal set-intersection would have removed a
model that demonstrably works. So the match is alias-aware, and the first test
below is that exact pair.

Every test here mocks the endpoint. A test that reached the network would be
slow, would fail offline, and would assert against whatever the account
happened to be entitled to that day.
"""

from __future__ import annotations

import sys
import types

import pytest

from lib import scene_ai


@pytest.fixture(autouse=True)
def _clear_cache():
    """The cache is module-level by design; tests must not inherit each other's."""
    scene_ai._AVAILABILITY_CACHE.clear()
    yield
    scene_ai._AVAILABILITY_CACHE.clear()


def _reported(monkeypatch, ids):
    monkeypatch.setattr(
        scene_ai, "_reported_claude_models", lambda *a, **k: set(ids) if ids is not None else None
    )


TABLE = [
    {"value": "claude-opus-5", "label": "Opus 5"},
    {"value": "claude-haiku-4-5", "label": "Haiku 4.5"},
]


class TestAliasMatching:
    def test_a_dated_snapshot_satisfies_the_alias(self, monkeypatch):
        # The real case: endpoint says dated, table says alias, call works.
        _reported(monkeypatch, ["claude-opus-5", "claude-haiku-4-5-20251001"])
        offered, verified = scene_ai.available_models(TABLE)
        assert verified is True
        assert [m["value"] for m in offered] == [
            "claude-opus-5",
            "claude-haiku-4-5",
        ]

    def test_a_point_release_is_NOT_a_date_and_must_not_match(self, monkeypatch):
        # `claude-fable-5-1` starts with `claude-fable-5-`, so a careless
        # prefix match would report Fable 5 as available when only 5.1 is.
        # The suffix has to look like a date (8 digits) to count.
        assert scene_ai._matches("claude-fable-5", {"claude-fable-5-1"}) is False
        assert scene_ai._matches("claude-fable-5", {"claude-fable-5"}) is True

    def test_an_exact_id_still_matches(self):
        assert scene_ai._matches("claude-opus-5", {"claude-opus-5"}) is True

    def test_an_unrelated_id_does_not(self):
        assert scene_ai._matches("claude-opus-5", {"claude-sonnet-4-6"}) is False


class TestFiltering:
    def test_a_model_the_key_cannot_see_is_dropped(self, monkeypatch):
        _reported(monkeypatch, ["claude-opus-5"])
        offered, verified = scene_ai.available_models(TABLE)
        assert verified is True
        assert [m["value"] for m in offered] == ["claude-opus-5"]


class TestFailSoft:
    """A verification step that can take the page down is worse than the
    problem it solves."""

    def test_no_answer_means_the_full_table_marked_unverified(self, monkeypatch):
        _reported(monkeypatch, None)  # no key, no network, provider 500
        offered, verified = scene_ai.available_models(TABLE)
        assert verified is False
        assert [m["value"] for m in offered] == [m["value"] for m in TABLE]

    def test_an_empty_intersection_is_treated_as_a_failed_check(self, monkeypatch):
        # If nothing matches, the check is broken far more likely than every
        # model having vanished at once — and an empty selector is unusable.
        _reported(monkeypatch, ["something-else-entirely"])
        offered, verified = scene_ai.available_models(TABLE)
        assert verified is False
        assert len(offered) == len(TABLE)

    def test_a_raising_client_becomes_unknown_not_an_exception(self, monkeypatch):
        """The swallow happens in `_reported_claude_models`, so callers never
        see an exception they would have to re-handle.

        The stub is the point. An `import anthropic` HERE would make this test
        require the SDK, and CI installs requirements.txt plus the leg's
        extras, which names no anthropic — so a test of the fail-soft path
        would itself fail for want of the thing whose absence it exists to
        tolerate. Stubbing `sys.modules` measures the same path on any set.
        """
        stub = types.ModuleType("anthropic")

        def boom(*a, **k):
            raise RuntimeError("network on fire")

        stub.Anthropic = boom
        monkeypatch.setitem(sys.modules, "anthropic", stub)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
        assert scene_ai._reported_claude_models() is None

    def test_the_sdk_not_being_installed_is_unknown_too(self, monkeypatch):
        """CI's actual state, and the deployed site's until E2's pins land:
        no anthropic on the path at all, so the import inside
        `_reported_claude_models` raises ModuleNotFoundError. That has to
        read as "unknown" like any other failure — an uncaught ImportError
        here would take down every page that builds a model selector.

        `None` in `sys.modules` is CPython's own "this import is blocked",
        which is a truer simulation than deleting the entry (the real SDK
        would just be re-imported from site-packages).
        """
        monkeypatch.setitem(sys.modules, "anthropic", None)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-a-real-key")
        assert scene_ai._reported_claude_models() is None

    def test_no_key_is_unknown_rather_than_an_empty_answer(self, monkeypatch):
        # "" and "no models" must not be confused: an unset key means the
        # check could not run, not that the key can call nothing.
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert scene_ai._reported_claude_models() is None


class TestCaching:
    def test_the_endpoint_is_consulted_once(self, monkeypatch):
        calls = {"n": 0}

        def counted(*a, **k):
            calls["n"] += 1
            return {"claude-opus-5", "claude-haiku-4-5-20251001"}

        monkeypatch.setattr(scene_ai, "_reported_claude_models", counted)
        scene_ai.available_models(TABLE)
        scene_ai.available_models(TABLE)
        scene_ai.available_models(TABLE)
        assert calls["n"] == 1, "the models endpoint was called more than once"

    def test_refresh_forces_a_recheck(self, monkeypatch):
        calls = {"n": 0}

        def counted(*a, **k):
            calls["n"] += 1
            return {"claude-opus-5", "claude-haiku-4-5-20251001"}

        monkeypatch.setattr(scene_ai, "_reported_claude_models", counted)
        scene_ai.available_models(TABLE)
        scene_ai.available_models(TABLE, refresh=True)
        assert calls["n"] == 2
