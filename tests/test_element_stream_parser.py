"""Pulling whole elements out of a scene JSON that is still being written.

This is what turns a spinner into watching it draw, and it is the piece where
a plausible-looking implementation is silently wrong. Two failure modes are
pinned here because both produce a canvas that simply never updates rather
than an error anyone would notice:

  * a `{` or `}` INSIDE a string value (``"text": "if (x) {y}"``) throws off a
    naive brace count, and label text containing braces is not exotic;
  * a stream arrives in arbitrary chunks — one character per delta is the
    worst realistic case — so any state the scan keeps has to survive across
    feeds. Restarting the scan at position 0 each time re-counts every brace
    already seen, which yields ZERO elements for small chunks while looking
    perfectly correct for large ones.
"""

from __future__ import annotations

import json

import pytest

from lib.scene_ai import ElementStreamParser

SCENE = {
    "type": "excalidraw",
    "elements": [
        {"id": "a", "type": "rectangle", "x": 0, "y": 0},
        {"id": "b", "type": "text", "text": "if (x) {y} else {z}"},
        {"id": "c", "type": "text", "text": 'she said "hi" and left'},
        {"id": "d", "type": "ellipse", "x": 10, "y": 10},
    ],
    "appState": {"viewBackgroundColor": "#fff"},
}
DOC = json.dumps(SCENE)


def _feed_in_chunks(text: str, size: int) -> list[dict]:
    parser = ElementStreamParser()
    out: list[dict] = []
    for i in range(0, len(text), size):
        out.extend(parser.feed(text[i:i + size]))
    return out


class TestItFindsEveryElement:
    @pytest.mark.parametrize("size", [1, 2, 3, 7, 13, 64, 4096])
    def test_whatever_the_chunk_size(self, size):
        # size=1 is the regression: it is what a token stream actually looks
        # like, and it is the case a position-resetting scan gets wrong.
        got = _feed_in_chunks(DOC, size)
        assert [e["id"] for e in got] == ["a", "b", "c", "d"], (
            f"chunk size {size} lost elements"
        )

    def test_braces_inside_a_string_do_not_split_an_element(self):
        got = _feed_in_chunks(DOC, 1)
        text_el = next(e for e in got if e["id"] == "b")
        assert text_el["text"] == "if (x) {y} else {z}"

    def test_escaped_quotes_inside_a_string_survive(self):
        got = _feed_in_chunks(DOC, 1)
        quoted = next(e for e in got if e["id"] == "c")
        assert quoted["text"] == 'she said "hi" and left'

    def test_elements_arrive_before_the_document_is_complete(self):
        # The entire point: the first element must be available long before
        # the closing brace of the whole scene.
        parser = ElementStreamParser()
        head = DOC[: DOC.index('{"id": "b"')]
        early = parser.feed(head)
        assert [e["id"] for e in early] == ["a"]
        assert not parser.finished


class TestItStopsAtTheEndOfTheArray:
    def test_appstate_objects_are_not_mistaken_for_elements(self):
        got = _feed_in_chunks(DOC, 1)
        assert len(got) == 4, "something after the elements array was emitted"
        assert all("viewBackgroundColor" not in e for e in got)

    def test_finished_is_set_once_the_array_closes(self):
        parser = ElementStreamParser()
        parser.feed(DOC)
        assert parser.finished

    def test_feeding_after_the_end_yields_nothing(self):
        parser = ElementStreamParser()
        parser.feed(DOC)
        assert parser.feed('{"id": "late"}') == []


class TestItToleratesRubbish:
    def test_a_malformed_element_is_dropped_not_fatal(self):
        # One bad object must not stall the stream: the shapes after it are
        # still worth drawing.
        broken = '{"type": "excalidraw", "elements": [{"id": "a",}, {"id": "b"}]}'
        got = _feed_in_chunks(broken, 1)
        assert [e["id"] for e in got] == ["b"]

    def test_no_elements_key_yields_nothing_and_does_not_raise(self):
        assert _feed_in_chunks('{"type": "excalidraw"}', 1) == []

    def test_an_empty_feed_is_harmless(self):
        parser = ElementStreamParser()
        assert parser.feed("") == []


class TestNormalisingAStreamedElement:
    """What the blocking path did and the streaming path first did not.

    OBSERVED on /ai-agent while streaming from gpt-6-astra: the canvas
    plateaued around 150 elements and appeared to delete one shape for every
    new one. `updateScene` reconciles BY ID — an element whose id already
    exists REPLACES the existing one — so a model that repeats ids caps the
    scene at the number of DISTINCT ids it emits, silently, with no error
    anywhere. Renaming the duplicate is what keeps both shapes.
    """

    def test_a_repeated_id_is_renamed_so_both_shapes_survive(self):
        from lib.scene_ai import _normalize_streamed

        seen = set()
        first = _normalize_streamed({"id": "a", "type": "rectangle"}, seen)
        second = _normalize_streamed({"id": "a", "type": "ellipse"}, seen)
        assert first["id"] == "a"
        assert second["id"] != "a", "the duplicate would have replaced the first"
        assert second["type"] == "ellipse"

    def test_a_missing_id_gets_one(self):
        from lib.scene_ai import _normalize_streamed

        got = _normalize_streamed({"type": "rectangle"}, set())
        assert isinstance(got["id"], str) and got["id"]

    def test_the_fields_excalidraw_needs_are_filled_in(self):
        # The blocking path got these from `_coerce_types`; streaming skipped
        # it entirely, so the two paths disagreed about what an element is.
        from lib.scene_ai import _normalize_streamed

        got = _normalize_streamed({"id": "a", "type": "rectangle"}, set())
        for field in ("version", "versionNonce", "seed", "isDeleted", "updated"):
            assert field in got, f"{field} missing — updateScene reconciles on these"

    def test_stringified_numbers_are_coerced(self):
        from lib.scene_ai import _normalize_streamed

        got = _normalize_streamed(
            {"id": "a", "type": "rectangle", "x": "10.5", "width": "20"}, set()
        )
        assert got["x"] == 10.5 and got["width"] == 20.0

    def test_a_non_dict_is_dropped_rather_than_dispatched(self):
        from lib.scene_ai import _normalize_streamed

        assert _normalize_streamed(["not", "an", "element"], set()) is None

    def test_distinct_ids_are_left_alone(self):
        from lib.scene_ai import _normalize_streamed

        seen = set()
        ids = [
            _normalize_streamed({"id": f"e{i}", "type": "rectangle"}, seen)["id"]
            for i in range(50)
        ]
        assert ids == [f"e{i}" for i in range(50)]

    def test_a_hundred_repeats_yield_a_hundred_distinct_shapes(self):
        # The plateau, directly: without renaming this scene is ONE element.
        from lib.scene_ai import _normalize_streamed

        seen = set()
        got = [
            _normalize_streamed({"id": "same", "type": "rectangle"}, seen)
            for _ in range(100)
        ]
        assert len({e["id"] for e in got}) == 100
