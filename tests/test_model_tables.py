"""The model registry in lib/scene_ai.py: one list, five tables that must agree.

Adding a model is five edits (CLAUDE_MODELS, pricing, budget, effort default,
effort capability), and a model missing from one of them fails somewhere
unhelpful: no price means `settle` records $0 and the estimate says "no
estimate"; no budget means a 32K fallback nobody chose. This file makes the
omission a test failure instead.

Claude Opus 5.5 (added 2026-09-22) is pinned by its own facts. MEASURED that
day from `GET /v1/models/claude-opus-5-5` on this deployment's key:
image_input true, effort low/medium/high/xhigh/max all true, 1M in / 128K out.
Its price and its `medium` default effort are from the model's launch notes.
"""

from __future__ import annotations

import pytest

from lib.scene_ai import (
    CLAUDE_EFFORT,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODELS,
    CLAUDE_PRICING,
    COMPARABLE_MODELS,
    EFFORT_CAPABLE,
    EFFORT_LEVELS,
    EFFORT_UTILISATION,
    MODEL_LABEL,
    PROVIDER_OF,
    VISION_MODELS,
    estimate_cost,
    supported_efforts,
)

CLAUDE_IDS = [m["value"] for m in CLAUDE_MODELS]


def test_the_corpus_is_not_empty():
    assert len(CLAUDE_IDS) >= 5, CLAUDE_IDS


@pytest.mark.parametrize("model", CLAUDE_IDS)
def test_every_claude_model_is_in_every_table(model):
    assert model in CLAUDE_PRICING, "unpriced: settle() would record $0"
    assert model in CLAUDE_MAX_TOKENS, "no budget: a 32K fallback nobody chose"
    assert model in CLAUDE_EFFORT, "no effort default for the selector"
    assert PROVIDER_OF[model] == "claude"
    assert model in MODEL_LABEL


def test_no_table_names_a_model_the_list_does_not_offer():
    offered = set(CLAUDE_IDS)
    for table in (CLAUDE_PRICING, CLAUDE_MAX_TOKENS, CLAUDE_EFFORT):
        assert set(table) == offered, set(table) ^ offered


class TestOpus55:
    MODEL = "claude-opus-5-5"

    def test_offered_on_all_three_ai_pages(self):
        assert self.MODEL in CLAUDE_IDS  # /ai-agent
        assert self.MODEL in {m["value"] for m in COMPARABLE_MODELS}  # /benchmark
        assert self.MODEL in VISION_MODELS  # /trace-image

    def test_is_not_the_default(self):
        # Index 0 is what an unattended visitor spends on, and every budget in
        # the table was measured on Opus 5. Moving 5.5 there is a decision.
        assert CLAUDE_MODELS[0]["value"] == "claude-opus-5"

    def test_price(self):
        assert CLAUDE_PRICING[self.MODEL] == (4.0, 20.0)

    def test_every_effort_level_is_offered(self):
        assert self.MODEL in EFFORT_CAPABLE
        assert supported_efforts(self.MODEL) == [e["value"] for e in EFFORT_LEVELS]

    def test_selector_starts_at_an_explicit_low(self):
        # Its API default is `medium`, unlike every other model here, so the
        # page sets the level rather than relying on the default.
        assert CLAUDE_EFFORT[self.MODEL] == "low"

    def test_none_is_priced_at_its_real_default_medium(self):
        est = estimate_cost(self.MODEL, "none", 24000)
        assert est["effort"] is None  # nothing is sent...
        assert est["fraction"] == EFFORT_UTILISATION["medium"]  # ...and medium runs

    def test_other_models_none_is_still_priced_as_high_like(self):
        est = estimate_cost("claude-opus-5", "none", 24000)
        assert est["fraction"] == EFFORT_UTILISATION["none"]
