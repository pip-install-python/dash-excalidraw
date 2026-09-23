"""/scene-viewer's parser: what it accepts, what it refuses, what it warns about.

The page's promise is that nothing Excalidraw would drop silently gets dropped
silently here. Each warning is pinned to the input that should raise it, and
each accepted shape to a real source of scene JSON in this repo.
"""

from __future__ import annotations

import json

import pytest

from lib.scene_json import (
    KNOWN_TYPES,
    SceneError,
    build_render,
    parse_scene_text,
)


def _rect(el_id="r1", **extra):
    return {"id": el_id, "type": "rectangle", "x": 0, "y": 0,
            "width": 100, "height": 60, **extra}


def _types(render):
    return [c["type"] for c in render["commands"]]


class TestWhatItAccepts:
    SCENE = {"type": "excalidraw", "version": 2, "elements": [_rect()],
             "appState": {"viewBackgroundColor": "#fff"}, "files": {}}

    def test_a_full_scene_envelope(self):
        # /trace-image's panel, serializedData, a .excalidraw file.
        assert parse_scene_text(json.dumps(self.SCENE))["elements"][0]["id"] == "r1"

    def test_a_bare_element_array(self):
        assert parse_scene_text(json.dumps([_rect()]))["elements"][0]["id"] == "r1"

    def test_a_fenced_model_reply_with_a_trailing_comma(self):
        reply = '```json\n{"elements": [' + json.dumps(_rect()) + ',]}\n```'
        assert len(parse_scene_text(reply)["elements"]) == 1

    def test_a_fenced_ARRAY(self):
        # The case `_extract_json_block` alone gets wrong: it finds the first
        # `{` and returns one element as if it were the scene.
        reply = "```json\n" + json.dumps([_rect("a"), _rect("b")]) + "\n```"
        assert [e["id"] for e in parse_scene_text(reply)["elements"]] == ["a", "b"]

    def test_prose_around_the_object(self):
        reply = "Here is your diagram:\n" + json.dumps(self.SCENE) + "\nEnjoy!"
        assert len(parse_scene_text(reply)["elements"]) == 1

    def test_serialized_data_quoted_once_too_often(self):
        # serializedData is a JSON string; json.dumps of it is what a Store or
        # a log hands you.
        assert len(parse_scene_text(json.dumps(json.dumps(self.SCENE)))["elements"]) == 1


class TestWhatItRefuses:
    @pytest.mark.parametrize("text", ["", "   ", None])
    def test_nothing(self, text):
        with pytest.raises(SceneError, match="Nothing to render"):
            parse_scene_text(text)

    def test_broken_json_says_where(self):
        with pytest.raises(SceneError, match=r"line \d+, column \d+"):
            parse_scene_text('{"elements": [}')

    def test_json_that_is_not_a_scene(self):
        with pytest.raises(SceneError, match="no `elements` key"):
            parse_scene_text('{"hello": "world"}')

    def test_a_library_file_is_pointed_at_the_library_page(self):
        with pytest.raises(SceneError, match="library file"):
            parse_scene_text('{"type": "excalidrawlib", "libraryItems": []}')

    def test_a_scalar(self):
        with pytest.raises(SceneError, match="int"):
            parse_scene_text("42")

    def test_oversize(self, monkeypatch):
        import lib.scene_json as mod

        monkeypatch.setattr(mod, "MAX_SCENE_BYTES", 10)
        with pytest.raises(SceneError, match="MB of JSON"):
            parse_scene_text(json.dumps([_rect()]))


class TestTheCommands:
    def test_a_plain_scene_is_reset_load_fit_in_that_order(self):
        render = build_render({"elements": [_rect()]}, token="t")
        assert _types(render) == ["resetScene", "updateScene", "scrollToContent"]
        assert render["notes"] == []
        ids = [c["id"] for c in render["commands"]]
        assert len(set(ids)) == len(ids), "a repeated command id is a no-op"

    def test_the_load_does_not_become_one_undo_step(self):
        load = build_render({"elements": [_rect()]})["commands"][1]
        assert load["payload"]["captureUpdate"] == "NEVER"

    def test_only_the_allowed_app_state_reaches_the_canvas(self):
        scene = {"elements": [_rect()], "appState": {
            "viewBackgroundColor": "#123456", "gridSize": 20,
            "theme": "dark", "viewModeEnabled": True, "zoom": {"value": 3}}}
        state = build_render(scene)["commands"][1]["payload"]["appState"]
        assert state == {"viewBackgroundColor": "#123456", "gridSize": 20}

    def test_inline_images_go_through_replace_files_not_add_files(self):
        scene = {
            "elements": [_rect(), {"id": "i", "type": "image", "fileId": "f1",
                                   "width": 10, "height": 10}],
            "files": {"f1": {"id": "f1", "dataURL": "data:image/png;base64,AAAA"}},
        }
        render = build_render(scene)
        assert _types(render) == ["resetScene", "updateScene", "replaceFiles",
                                  "scrollToContent"]
        payload = render["commands"][2]["payload"]
        assert payload == {"f1": {"dataURL": "data:image/png;base64,AAAA",
                                  "mimeType": "image/png"}}
        assert render["notes"] == []

    def test_an_empty_scene_clears_and_does_not_try_to_fit(self):
        render = build_render({"elements": []})
        assert _types(render) == ["resetScene", "updateScene"]
        assert any("Nothing visible" in n for n in render["notes"])


class TestWhatItSaysOutLoud:
    """Every one of these is something Excalidraw would drop WITHOUT a word."""

    def _notes(self, elements, **scene):
        return " | ".join(build_render({"elements": elements, **scene})["notes"])

    def test_unknown_types_and_selection(self):
        notes = self._notes([_rect(), {"id": "x", "type": "sparkle"},
                             {"id": "s", "type": "selection"}])
        assert "type `sparkle`" in notes and "`selection`" in notes

    def test_unknown_types_are_not_sent(self):
        render = build_render({"elements": [_rect(), {"id": "x", "type": "sparkle"}]})
        sent = render["commands"][1]["payload"]["elements"]
        assert [e["id"] for e in sent] == ["r1"]
        assert render["drawn"] == 1

    def test_invisibly_small(self):
        notes = self._notes([_rect(), _rect("z", width=0, height=0),
                             {"id": "l", "type": "line", "points": [[0, 0]]}])
        assert "2 elements skipped as invisibly small" in notes

    def test_deleted_are_kept_but_not_counted_as_drawn(self):
        render = build_render({"elements": [_rect(), _rect("d", isDeleted=True)]})
        assert render["drawn"] == 1
        assert len(render["commands"][1]["payload"]["elements"]) == 2
        assert "isDeleted" in " ".join(render["notes"])

    def test_duplicate_ids(self):
        assert "1 duplicate id" in self._notes([_rect("a"), _rect("a")])

    def test_images_the_externalized_form_nulled(self):
        # What `externalizedSerializedData` hands back for a scene that held
        # an inline image: the entry survives, its bytes do not.
        notes = self._notes(
            [{"id": "i", "type": "image", "fileId": "f1", "width": 9, "height": 9}],
            files={"f1": {"id": "f1", "dataURL": None}},
        )
        assert "1 image has no loadable bytes" in notes

    def test_a_script_url_is_not_loadable(self):
        render = build_render({
            "elements": [{"id": "i", "type": "image", "fileId": "f",
                          "width": 9, "height": 9}],
            "files": {"f": {"dataURL": "javascript:alert(1)"}},
        })
        assert "replaceFiles" not in _types(render)


def test_the_pages_own_sample_survives_its_own_filter(monkeypatch):
    """Corpus check: the sample the page opens on must render with no notes.
    Loaded the way tests/test_provider_keys.py loads page modules."""
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "docs" / "scene-viewer" / "scene_viewer.py"
    spec = importlib.util.spec_from_file_location("posture_scene_viewer", path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "posture_scene_viewer", module)
    spec.loader.exec_module(module)

    scene = module.SAMPLE_SCENE
    assert len(scene["elements"]) >= 10, "sample is empty — the check would be vacuous"
    assert {e["type"] for e in scene["elements"]} <= KNOWN_TYPES
    render = build_render(parse_scene_text(module.SAMPLE_TEXT))
    assert render["notes"] == [], render["notes"]
    assert render["drawn"] == len(scene["elements"])
