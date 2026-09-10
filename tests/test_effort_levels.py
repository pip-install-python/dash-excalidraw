"""Effort levels a model will actually accept.

`EFFORT_CAPABLE` answers "does this model take the parameter at all", which
was enough while the only exception was Haiku 4.5 rejecting it outright. It is
not enough for a model with a HOLE in the middle of its range.

MEASURED 2026-09-10 from `GET /v1/models/{id}` on this deployment's key:
claude-sonnet-4-6 reports ``effort.xhigh.supported: false`` while low, medium,
high and max are all true. Every other model in CLAUDE_MODELS reports either a
full range or no effort support at all. The selector was offering `xhigh` for
that model, so picking it sent a 400 — a provider error the page could not
explain, for a choice the page itself had presented.
"""

from __future__ import annotations

import pytest

from lib.scene_ai import (
    CLAUDE_MODELS,
    EFFORT_CAPABLE,
    EFFORT_LEVELS,
    EFFORT_UNSUPPORTED,
    supported_efforts,
)

ALL_LEVELS = [e["value"] for e in EFFORT_LEVELS]


class TestTheMeasuredHole:
    def test_sonnet_46_does_not_offer_xhigh(self):
        offered = supported_efforts("claude-sonnet-4-6")
        assert "xhigh" not in offered

    def test_it_keeps_every_other_level(self):
        offered = supported_efforts("claude-sonnet-4-6")
        for level in ALL_LEVELS:
            if level != "xhigh":
                assert level in offered, f"{level} was dropped along with xhigh"

    def test_no_other_model_has_a_hole(self):
        # If a second model grows one, this fails and the person adding it has
        # to say so here rather than discover it as a 400 in production.
        assert set(EFFORT_UNSUPPORTED) == {"claude-sonnet-4-6"}


class TestTheRestAreUnchanged:
    def test_models_that_reject_the_parameter_offer_only_none(self):
        assert supported_efforts("claude-haiku-4-5") == ["none"]

    def test_fully_capable_models_offer_everything(self):
        full = [
            m["value"]
            for m in CLAUDE_MODELS
            if m["value"] in EFFORT_CAPABLE
            and m["value"] not in EFFORT_UNSUPPORTED
        ]
        assert full, "corpus empty — the assertion below would be vacuous"
        for model in full:
            assert supported_efforts(model) == ALL_LEVELS

    @pytest.mark.parametrize("model", [m["value"] for m in CLAUDE_MODELS])
    def test_every_model_offers_at_least_one_level(self, model):
        # "none" always survives: it means send no output_config at all, which
        # every model accepts by definition.
        assert supported_efforts(model)
        assert "none" in supported_efforts(model)
