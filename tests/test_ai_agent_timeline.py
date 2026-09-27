"""The /ai-agent scene library, and the deck/timeline wiring.

The library is local-only: on the public site (no provider keys) it must
neither list nor create anything. Locally it keeps scenes in draw order so
the timeline can replay them."""
from __future__ import annotations

import importlib
import json

import pytest


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SCENES_DB", str(tmp_path / "scenes.sqlite"))
    from lib import scene_library
    return importlib.reload(scene_library)


def test_library_round_trip_keeps_draw_order(lib):
    els = [{"id": f"e{i}", "type": "rectangle"} for i in range(5)]
    sid = lib.save(els, prompt="a  flowchart   of onboarding", provider="claude",
                   model="claude-opus-5-5", effort="low", max_tokens=32000, seed=3)
    row = lib.get(sid)
    assert [e["id"] for e in row["elements"]] == ["e0", "e1", "e2", "e3", "e4"]
    assert row["title"] == "a flowchart of onboarding" and row["seed"] == 3
    opts = lib.options()
    assert opts[0]["value"] == str(sid) and "5 el" in opts[0]["label"]


def test_library_refuses_an_empty_scene(lib):
    with pytest.raises(ValueError):
        lib.save([])


def test_the_public_site_never_touches_the_library(app_module, tmp_path, monkeypatch):
    db = tmp_path / "never.sqlite"
    monkeypatch.setenv("AI_SCENES_DB", str(db))
    import sys
    page = next(m for name, m in sys.modules.items() if name.endswith("ai_agent") and hasattr(m, "_save_scene"))
    monkeypatch.setattr(page, "ANY_KEY", False)
    assert page._list_scenes(0) == []
    assert page._save_scene(1, {"elements": [{"id": "x"}]}, "p", "claude", "m", "low", 1000, 1)[1] \
        == "The scene library is local-only."
    assert page._load_scene("1") == (page.no_update,) * 4
    assert not db.exists()


def test_save_then_load_puts_the_scene_back_on_the_canvas(app_module, tmp_path, monkeypatch):
    monkeypatch.setenv("AI_SCENES_DB", str(tmp_path / "scenes.sqlite"))
    import sys
    page = next(m for name, m in sys.modules.items() if name.endswith("ai_agent") and hasattr(m, "_save_scene"))
    monkeypatch.setattr(page, "ANY_KEY", True)
    els = [{"id": "a"}, {"id": "b"}]
    opts, status, color = page._save_scene(1, {"elements": els}, "draw a bee", "claude", "m", "low", 8000, 2)
    assert color == "green" and opts
    cmd, status, color, prompt = page._load_scene(opts[0]["value"])
    assert cmd["type"] == "updateScene" and cmd["payload"]["elements"] == els
    assert cmd["id"].startswith("lib-")  # not "tl-": the timeline must capture it
    assert prompt == "draw a bee"


def test_deck_bridge_assets_ship(app_module):
    from pathlib import Path
    root = Path(app_module.__file__).resolve().parent
    bridge = (root / "assets" / "deck_bridge.js").read_text()
    for op in ('"state"', '"step"', '"set"', '"act"', "set_props"):
        assert op in bridge
    actions = (root / "assets" / "deck_bridge_ai_agent.js").read_text()
    for name in ("generate", "preset", "focus_prompt", "replay", "save"):
        assert name + ":" in actions


def test_timeline_callbacks_are_registered(app_module):
    from dash import _callback
    keys = list(getattr(app_module.app, "callback_map", {}).keys()) + list(_callback.GLOBAL_CALLBACK_MAP)
    cbs = json.dumps(keys)
    for needle in ("ai-history.data", "ai-timeline.max", "ai-deck-mirror.data", "ai-library.data"):
        assert needle in cbs, needle
