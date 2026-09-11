"""/benchmark's brakes, and the property that makes them honest.

A Stop button is only truthful if the thing it stops can actually be stopped.
/benchmark used to run its variants through the BLOCKING `call_model` in a
thread pool: a button there could have disabled the spinner and reported
"stopped" while six models carried on to their full budgets, billing all the
way. The conversion to streamed runs is therefore not a nicety attached to the
feature — it IS the feature, and `test_the_page_cannot_go_back_to_blocking_calls`
is what keeps the two from drifting apart.

One click here is up to six paid calls at once, which is why this page gets
the brakes even though /ai-agent got them first.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from docs.benchmark import benchmark
from lib.scene_ai import MODEL_PRICING

SOURCE = Path(__file__).resolve().parent.parent / "docs" / "benchmark" / "benchmark.py"


class TestTheStopIsReal:
    def test_it_cancels_every_variant(self, monkeypatch):
        cancelled = []
        monkeypatch.setattr(
            benchmark.scene_stream, "cancel", lambda rid: cancelled.append(rid) or True
        )
        cells = [
            {"id": "r1", "label": "a", "model": "claude-opus-5", "cursor": 0},
            {"id": "r2", "label": "b", "model": "gpt-6-astra", "cursor": 0},
            {"id": "r3", "label": "c", "model": "claude-opus-5", "cursor": 0},
        ]
        message, color, next_cells, tick_disabled = benchmark._stop(1, cells)

        assert cancelled == ["r1", "r2", "r3"], (
            "a sweep is six bills; stopping some of them is not stopping"
        )
        assert tick_disabled is True
        assert color == "yellow"
        assert "Stopped 3 variants" in message
        assert all(c["cancelled"] for c in next_cells)

    def test_it_says_what_survives(self, monkeypatch):
        # A half-finished sweep is still a comparison, and usually the reason
        # for stopping. Promising that in words matters: a user who thinks
        # Stop discards the work will sit through a run they wanted to end.
        monkeypatch.setattr(benchmark.scene_stream, "cancel", lambda rid: True)
        message, _, _, _ = benchmark._stop(
            1, [{"id": "r1", "label": "a", "model": "claude-opus-5", "cursor": 0}]
        )
        assert "kept" in message
        assert "no further tokens" in message

    def test_stopping_nothing_is_not_an_error(self):
        message, _, _, tick_disabled = benchmark._stop(1, None)
        assert tick_disabled is True
        assert message is not None  # a no_update sentinel, not an exception

    def test_a_run_that_had_already_finished_is_not_counted(self, monkeypatch):
        # `cancel` returns False for a run the store no longer holds. Counting
        # it would report brakes that were never applied.
        monkeypatch.setattr(benchmark.scene_stream, "cancel", lambda rid: rid == "live")
        cells = [
            {"id": "live", "label": "a", "model": "claude-opus-5", "cursor": 0},
            {"id": "gone", "label": "b", "model": "claude-opus-5", "cursor": 0},
        ]
        message, _, _, _ = benchmark._stop(1, cells)
        assert "Stopped 1 variant." in message


class TestTheStopStaysHonest:
    def test_the_page_cannot_go_back_to_blocking_calls(self):
        """The guard that keeps the button from becoming a lie.

        `call_model` and a thread pool cannot be interrupted mid-call, so a
        Stop over them would disable the spinner while the models kept
        spending. If this page ever imports them again, the button needs
        rewriting or removing — not quietly leaving in place.
        """
        source = SOURCE.read_text(encoding="utf-8")
        assert "scene_stream.start" in source, (
            "corpus check — if the page stopped streaming, the assertions "
            "below would pass for the wrong reason"
        )
        for blocking in ("call_model", "concurrent.futures", "ThreadPoolExecutor"):
            assert blocking not in source, (
                f"{blocking} is back in /benchmark; its calls cannot be "
                f"interrupted, so the Stop button would not stop the spending"
            )

    def test_stop_is_enabled_exactly_when_the_others_are_not(self):
        # The one control that inverts. Getting this backwards leaves the
        # brake greyed out during the only moment it is useful.
        while_sweeping = benchmark._lock_controls(False)
        while_idle = benchmark._lock_controls(True)
        assert while_sweeping[2] is False, "Stop disabled while a sweep runs"
        assert while_idle[2] is True, "Stop enabled when there is nothing to stop"
        assert while_sweeping[0] is True and while_idle[0] is False


class TestTheCellHeader:
    BASE = {"id": "r1", "label": "effort=low", "model": "claude-opus-5"}

    def test_a_stopped_cell_says_so(self):
        head = benchmark._head(
            self.BASE,
            {"all": [{}, {}], "elapsed": 3.0, "done": True, "cancelled": True},
        )
        assert "stopped" in str(head)

    def test_a_running_cell_says_drawing(self):
        head = benchmark._head(
            self.BASE, {"all": [{}], "elapsed": 1.0, "done": False}
        )
        assert "drawing" in str(head)

    def test_an_error_replaces_the_numbers(self):
        head = benchmark._head(self.BASE, {"error": "RuntimeError: nope"})
        rendered = str(head)
        assert "RuntimeError: nope" in rendered
        assert "drawing" not in rendered

    def test_truncation_is_named_not_left_as_a_stop_reason(self):
        head = benchmark._head(
            self.BASE,
            {
                "all": [{}],
                "elapsed": 9.0,
                "done": True,
                "meta": {
                    "output_tokens": 24000,
                    "input_tokens": 500,
                    "max_tokens": 24000,
                    "stop_reason": "max_tokens",
                },
            },
        )
        assert "TRUNCATED" in str(head)

    def test_a_lost_element_is_surfaced(self):
        head = benchmark._head(
            self.BASE, {"all": [{}], "elapsed": 1.0, "done": False, "lost": 2}
        )
        assert "lost" in str(head)


class TestPerCellCost:
    def test_each_cell_is_priced_by_its_own_model(self):
        # On the model axis the cells are different models at different rates;
        # pricing them all at the page's model select would be wrong by up to
        # 40x, which is the spread between the cheapest and dearest offered.
        meta = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
        opus = benchmark._cell_cost("claude-opus-5", meta)
        luna = benchmark._cell_cost("gpt-5.6-luna", meta)
        assert opus != luna
        assert opus == pytest.approx(sum(MODEL_PRICING["claude-opus-5"]))

    def test_no_meta_prices_at_zero_rather_than_raising(self):
        # A cell still drawing has no usage yet; the header renders anyway.
        assert benchmark._cell_cost("claude-opus-5", None) == 0.0


class TestTheSlots:
    def test_there_is_one_slot_per_possible_variant(self):
        # Slots are static so a callback can write into them; a variant with
        # no slot would silently never render.
        source = SOURCE.read_text(encoding="utf-8")
        assert "range(MAX_VARIANTS)" in source
        assert benchmark.MAX_VARIANTS == 6

    def test_every_slot_id_is_pattern_matched(self):
        source = SOURCE.read_text(encoding="utf-8")
        for kind in ("bm-slot", "bm-head", "bm-canvas"):
            assert re.search(rf'\{{"type": "{kind}", "index": index\}}', source), (
                f"{kind} is not a pattern-matching id, so one callback cannot "
                f"address all six cells"
            )
