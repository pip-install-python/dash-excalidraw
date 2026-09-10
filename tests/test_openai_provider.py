"""`_call_openai` — the ChatGPT path, with the client mocked.

The point of this file is that /benchmark can put a Claude cell and a ChatGPT
cell in ONE sweep and call the difference between them a finding. That is only
true if the two calls are configured the same way, so what is pinned here is
not "the SDK was called" but the MAPPING: the page's three controls (model,
effort, max tokens) landing on the right three Responses-API fields, and a
`meta` that comes back the same shape Claude's does. A mismatch would not
raise — it would render two panels whose difference was partly configuration.

Nothing here reaches the network, and nothing here requires the `openai`
package to be installed. The stub goes into `sys.modules`, so the local
`from openai import OpenAI` inside `_call_openai` resolves to it. Same lesson
as tests/test_model_availability.py: a test that needs the SDK cannot run on
the install set where its absence matters.
"""

from __future__ import annotations

import sys
import types

import pytest

from lib import scene_ai


class _Usage:
    def __init__(self, i=1234, o=5678):
        self.input_tokens = i
        self.output_tokens = o


class _Response:
    def __init__(self, text='{"type": "excalidraw"}', status="completed", reason=None):
        self.output_text = text
        self.status = status
        self.usage = _Usage()
        self.incomplete_details = types.SimpleNamespace(reason=reason)


class _Recorder:
    """Captures the request the code BUILDS, which is the thing under test."""

    def __init__(self, response=None):
        self.kwargs = None
        self.api_key = None
        self._response = response or _Response()

    def __call__(self, *, api_key=None, **_):
        self.api_key = api_key
        return self

    @property
    def responses(self):
        return self

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self._response


@pytest.fixture
def client(monkeypatch):
    rec = _Recorder()

    def _install(response=None):
        if response is not None:
            rec._response = response
        stub = types.ModuleType("openai")
        stub.OpenAI = rec
        monkeypatch.setitem(sys.modules, "openai", stub)
        monkeypatch.setenv("CHATGPT_API_KEY", "sk-chatgpt-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        return rec

    rec.install = _install
    return rec


class TestTheKey:
    """Two accepted names, and a definite order between them."""

    def test_chatgpt_api_key_is_preferred(self, client, monkeypatch):
        client.install()
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-should-lose")
        scene_ai._call_openai("gpt-6-astra", "draw a cat")
        assert client.api_key == "sk-chatgpt-test"

    def test_openai_api_key_is_the_fallback(self, client, monkeypatch):
        client.install()
        monkeypatch.delenv("CHATGPT_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        scene_ai._call_openai("gpt-6-astra", "draw a cat")
        assert client.api_key == "sk-openai-test"

    def test_neither_key_names_both(self, client, monkeypatch):
        client.install()
        monkeypatch.delenv("CHATGPT_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError) as exc:
            scene_ai._call_openai("gpt-6-astra", "draw a cat")
        # Someone hitting this needs to know which name to set, and that the
        # other one would also do.
        assert "CHATGPT_API_KEY" in str(exc.value)
        assert "OPENAI_API_KEY" in str(exc.value)


class TestTheControlsReachTheRightFields:
    def test_the_three_controls_map_onto_three_fields(self, client):
        client.install()
        scene_ai._call_openai("gpt-6-astra", "draw a cat", 32000, "high")
        k = client.kwargs
        assert k["model"] == "gpt-6-astra"
        assert k["max_output_tokens"] == 32000
        assert k["reasoning"] == {"effort": "high"}
        # `instructions` + `input`, not a system message in a messages list —
        # that is the Responses API shape and the reason it was chosen.
        assert k["instructions"] == scene_ai.SYSTEM_PROMPT
        assert k["input"] == "draw a cat"

    def test_effort_none_sends_no_reasoning_field_at_all(self, client):
        # "none" is a real choice meaning "the model's own default", so the
        # parameter must be ABSENT rather than present-and-null.
        client.install()
        scene_ai._call_openai("gpt-6-astra", "draw a cat", 24000, "none")
        assert "reasoning" not in client.kwargs

    def test_the_models_own_default_effort_applies(self, client):
        client.install()
        scene_ai._call_openai("gpt-5.6-luna", "draw a cat", 24000, None)
        assert client.kwargs["reasoning"] == {
            "effort": scene_ai.MODEL_EFFORT["gpt-5.6-luna"]
        }

    def test_an_unreadable_budget_falls_back_instead_of_raising(self, client):
        # The `int("64.000")` regression, on the second provider. This is the
        # PAID path: it must send a known-safe number, not raise after the
        # user has committed to spending.
        client.install()
        scene_ai._call_openai("gpt-6-astra", "draw a cat", "abc")
        assert client.kwargs["max_output_tokens"] == scene_ai.OPENAI_MAX_TOKENS[
            "gpt-6-astra"
        ]

    def test_grouped_digits_are_parsed_the_same_way_as_claude(self, client):
        client.install()
        scene_ai._call_openai("gpt-6-astra", "draw a cat", "64.000")
        assert client.kwargs["max_output_tokens"] == 64000


class TestTruncation:
    """A 200 that is not a complete answer."""

    def test_hitting_the_budget_is_explained_not_parsed(self, client):
        client.install(_Response(text='{"type": "excal', status="incomplete",
                                 reason="max_output_tokens"))
        with pytest.raises(ValueError) as exc:
            scene_ai._call_openai("gpt-6-astra", "draw a cat", 24000)
        msg = str(exc.value)
        assert "24,000" in msg, "the message must quote the budget that was hit"
        # Handing half-written JSON to the parser fails several frames from
        # the cause, which is why this is caught here instead.
        assert "reasoning AND output" in msg

    def test_other_incomplete_reasons_still_raise(self, client):
        client.install(_Response(status="incomplete", reason="content_filter"))
        with pytest.raises(ValueError, match="content_filter"):
            scene_ai._call_openai("gpt-6-astra", "draw a cat")


class TestMetaParity:
    """/benchmark renders both providers through one code path."""

    def test_the_meta_has_the_same_keys_as_claudes(self, client):
        client.install()
        _, meta = scene_ai._call_openai("gpt-6-astra", "draw a cat", 24000, "low")
        expected = {
            "model", "effort", "effort_ignored", "max_tokens",
            "input_tokens", "output_tokens", "cache_read", "stop_reason",
        }
        assert set(meta) == expected

    def test_it_reports_the_effort_actually_sent(self, client):
        client.install()
        _, meta = scene_ai._call_openai("gpt-6-astra", "draw a cat", 24000, "none")
        assert meta["effort"] == "none"
        assert meta["effort_ignored"] is False

    def test_usage_comes_from_the_response_not_the_request(self, client):
        # Reading these back off the request would make the panel echo what we
        # asked for, and a cost computed from them would always be "correct".
        client.install()
        _, meta = scene_ai._call_openai("gpt-6-astra", "draw a cat", 24000, "low")
        assert (meta["input_tokens"], meta["output_tokens"]) == (1234, 5678)
        assert meta["max_tokens"] == 24000

    def test_the_text_is_the_responses_api_output_text(self, client):
        client.install(_Response(text='{"type": "excalidraw", "elements": []}'))
        text, _ = scene_ai._call_openai("gpt-6-astra", "draw a cat")
        assert text == '{"type": "excalidraw", "elements": []}'


class TestDispatch:
    def test_call_model_routes_a_chatgpt_id_here(self, client):
        client.install()
        scene_ai.call_model("gpt-5.6-terra", "draw a cat", 32000, "medium")
        assert client.kwargs["model"] == "gpt-5.6-terra"

    def test_call_model_refuses_a_model_it_cannot_compare(self):
        # Gemini has no price and no budget/effort controls, so a comparison
        # cell for it could show a drawing but never an honest cost.
        with pytest.raises(ValueError, match="COMPARABLE_MODELS"):
            scene_ai.call_model("gemini-2.5-pro", "draw a cat")
