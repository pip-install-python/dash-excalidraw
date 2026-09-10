"""`coerce_budget` — the parser standing in front of a paid API call.

The regression this file exists for, measured 2026-09-10 on a running app:
`dmc.NumberInput` does not hand a callback an int. Mid-edit it hands over
whatever is in the box, and the box held the string ``"64.000"``. Both AI
pages did ``int(max_tokens or ...)``, which raises rather than returning
anything — including inside `_call_claude`, which is the PAID path.

On the deployed build that raise is caught by `_generate`'s `except` and shown
as a red "claude call failed: invalid literal for int() with base 10:
'64.000'". Not an outage, but a failure whose message gives the user no way to
tell that their own typing caused it.

Two things are worth pinning beyond "it does not raise":

  1. **Which reading of "64.000" wins.** As a decimal it is 64 tokens; as
     grouped digits it is 64,000. A thousand-fold difference in what gets sent
     and then billed, so the choice is asserted rather than left to whichever
     parser happens to run.
  2. **That the value is clamped**, so the budget reaching the API is always
     inside the control's own range.
"""

from __future__ import annotations

import pytest

from lib.scene_ai import (
    BUDGET_MAX,
    BUDGET_MIN,
    CLAUDE_MAX_TOKENS,
    coerce_budget,
    estimate_cost,
)


class TestTheStringThatCrashedIt:
    def test_grouped_digits_read_as_thousands_not_as_a_decimal(self):
        # The exact value from the traceback. 64000, never 64.
        assert coerce_budget("64.000") == 64000

    @pytest.mark.parametrize("value", ["1,234", "128.000", "24 000"])
    def test_other_separator_shapes_survive(self, value):
        assert coerce_budget(value) is not None

    def test_the_estimate_prices_it_without_raising(self):
        est = estimate_cost("claude-opus-5", "low", "64.000")
        assert est["priced"] is True
        assert est["budget"] == 64000


class TestWhenItCannotBeRead:
    """An unreadable box is a normal mid-edit state, not an error."""

    @pytest.mark.parametrize("value", ["", "   ", "abc", None, True, float("nan")])
    def test_returns_the_default_rather_than_raising(self, value):
        assert coerce_budget(value) is None
        assert coerce_budget(value, 24000) == 24000

    def test_the_estimate_says_which_thing_is_missing(self):
        # A caller needs to tell "no budget yet" from "no price for this
        # model" — they read very differently to someone about to spend.
        assert estimate_cost("claude-opus-5", "low", "abc")["reason"] == "budget"
        assert estimate_cost("gemini-2.5-pro", "low", 24000)["reason"] == "model"

    def test_the_paid_path_falls_back_to_the_model_default(self):
        # `_call_claude` passes the model's own budget as the default, so an
        # unreadable box sends a known-safe number instead of raising.
        for _model, default in CLAUDE_MAX_TOKENS.items():
            assert coerce_budget("abc", default) == default


class TestClamping:
    def test_above_the_range_comes_down_to_the_ceiling(self):
        assert coerce_budget("999999") == BUDGET_MAX

    def test_below_the_range_comes_up_to_the_floor(self):
        assert coerce_budget("500") == BUDGET_MIN

    def test_the_estimate_prices_the_clamped_value_not_the_raw_one(self):
        # The label must quote what will actually be sent. Pricing 999,999
        # tokens while the request sends 128,000 would over-quote by 8x.
        est = estimate_cost("claude-opus-5", "low", "999999")
        assert est["budget"] == BUDGET_MAX
        at_max = estimate_cost("claude-opus-5", "low", BUDGET_MAX)["ceiling"]
        assert est["ceiling"] == pytest.approx(at_max)


class TestOrdinaryValues:
    @pytest.mark.parametrize(
        "value,expected",
        [(24000, 24000), (24000.0, 24000), ("24000", 24000), ("  8000 ", 8000)],
    )
    def test_pass_through_unchanged(self, value, expected):
        assert coerce_budget(value) == expected
