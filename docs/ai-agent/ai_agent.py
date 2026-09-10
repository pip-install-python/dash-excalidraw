"""AI agent: turn a prompt into an Excalidraw scene via Claude, ChatGPT or Gemini.

Uses the command dispatch pattern (`command: updateScene`) — no component
remount, no key-hack needed on the canvas. The same page compares Claude
Opus 4.7 / Sonnet 4.6 against GPT-6 Astra and Gemini 2.5 Flash / Pro.

Ship-readiness checklist for using this in your own production app:

1. Set env vars:
     ANTHROPIC_API_KEY=...
     CHATGPT_API_KEY=...      # OPENAI_API_KEY is accepted as a fallback
     GEMINI_API_KEY=...
   All three are optional — the page disables the corresponding provider
   if its key is missing, and says which name it looked for.

2. This page calls the LLM synchronously inside a Dash callback. For
   production-grade UX, wrap with a background task queue (Celery / RQ
   / Dramatiq) or Dash's `background=True` long-callback machinery. The
   code here prioritizes clarity over throughput.

3. The prompt template is a starting point — tune `SYSTEM_PROMPT` for
   your domain. Prompt caching is active on Claude calls because the
   system prompt is stable across requests.
"""

from __future__ import annotations

import json
import os
import re
import time
import traceback
import uuid
from typing import Any, Dict

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update

from dash_excalidraw import DashExcalidraw
from lib import scene_stream
from lib.scene_ai import (  # shared with /benchmark — see lib/scene_ai.py
    CLAUDE_EFFORT,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODELS,
    CLAUDE_PRICING,
    EFFORT_CAPABLE,
    EFFORT_LEVELS,
    MODEL_EFFORT,
    MODEL_MAX_TOKENS,
    OPENAI_MODELS,
    available_models,
    call_model,
    estimate_cost,
    format_money,
    supported_efforts,
    GEMINI_MAX_TOKENS,
    GEMINI_MODELS,
    SYSTEM_PROMPT,
    _call_gemini,
    _cleanup_json,
    _coerce_types,
    _extract_json_block,
    _parse_and_normalize,
    _spend_allowed,
)
from docs._shared import canvas_frame, sync_canvas_theme

sync_canvas_theme("ai-canvas")

def offered_claude_models():
    """The models this deployment's key can actually call.

    CALLED FROM A CALLBACK, NEVER AT IMPORT. Page modules are imported while
    Dash registers pages, so a module-level call here put an outbound request
    to api.anthropic.com on the BOOT path — every start of the app blocked on
    a third party being reachable, and the answer was then frozen for the life
    of the process. It was visible in the boot log, one line under
    "Loading docs/ai-agent/ai-agent.md":

        INFO:httpx:HTTP Request: GET https://api.anthropic.com/v1/models...

    `available_models` caches, so calling it per callback costs one request
    for the process and no more. `verified` False means the check could not
    run — the full table is offered and the page SAYS so rather than implying
    it was checked.
    """
    return available_models(CLAUDE_MODELS)

# ---------------------------------------------------------------------------
# Prompt template (domain-specific instructions for producing Excalidraw JSON)
# ---------------------------------------------------------------------------

HAS_CLAUDE_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
# CHATGPT_API_KEY is this site's name; OPENAI_API_KEY is the SDK's own and is
# accepted so a machine that already exports one needs no second copy.
HAS_CHATGPT_KEY = bool(os.environ.get("CHATGPT_API_KEY")) or bool(
    os.environ.get("OPENAI_API_KEY")
)
HAS_GEMINI_KEY = bool(os.environ.get("GEMINI_API_KEY")) or bool(
    os.environ.get("GOOGLE_API_KEY")
)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _benchmark_status(provider, model, element_count, elapsed, meta) -> str:
    """One line carrying everything a sweep needs to be compared.

    Elements alone say nothing about whether a setting was worth it — the
    interesting question is elements per second and per dollar, at a given
    effort and budget. So the line reports the settings ACTUALLY applied
    (which is not always what was asked: effort is silently dropped on models
    that reject it) alongside tokens, latency and an estimated cost.
    """
    plural = "s" if element_count != 1 else ""
    head = f"{model} — {element_count} element{plural} in {elapsed:.0f}s"
    if not meta:
        return f"Generated via {provider} / {head}."

    bits = [f"effort={meta['effort']}", f"max_tokens={meta['max_tokens']:,}"]
    if meta.get("effort_ignored"):
        bits.append("(effort ignored — model rejects it)")

    out_tok, in_tok = meta["output_tokens"], meta["input_tokens"]
    bits.append(f"{out_tok:,} out / {in_tok:,} in")
    if meta.get("cache_read"):
        bits.append(f"{meta['cache_read']:,} cached")

    price = CLAUDE_PRICING.get(model)
    if price and (out_tok or in_tok):
        cost = (in_tok * price[0] + out_tok * price[1]) / 1_000_000
        # Estimate, not a bill — see CLAUDE_PRICING.
        bits.append(f"~${cost:.3f}")

    if element_count:
        bits.append(f"{elapsed / element_count:.1f}s/element")

    if meta.get("stop_reason") and meta["stop_reason"] != "end_turn":
        bits.append(f"stop={meta['stop_reason']}")

    return f"{head}  ·  " + "  ·  ".join(bits)


def _format_parse_error(raw: str, exc: json.JSONDecodeError) -> str:
    """Show a window of text around the failure position so the Parsed tab
    actually helps you understand what broke."""
    pos = exc.pos or 0
    start = max(0, pos - 120)
    end = min(len(raw), pos + 120)
    pointer = " " * (pos - start) + "^"
    return (
        f"JSON parse error: {exc.msg}\n"
        f"  at line {exc.lineno}, column {exc.colno} (char {pos})\n\n"
        f"--- context (±120 chars) ---\n"
        f"{raw[start:end]}\n"
        f"{pointer}\n"
        f"--- end context ---\n\n"
        f"Length of model response: {len(raw)} chars.\n"
        f"Try switching to a different model, shortening your prompt, or "
        f"asking for a simpler diagram."
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _provider_status():
    items = []
    items.append(
        dmc.Badge(
            "Claude: ready" if HAS_CLAUDE_KEY else "Claude: missing ANTHROPIC_API_KEY",
            color="green" if HAS_CLAUDE_KEY else "red",
            variant="light",
            size="sm",
        )
    )
    items.append(
        dmc.Badge(
            "ChatGPT: ready"
            if HAS_CHATGPT_KEY
            else "ChatGPT: missing CHATGPT_API_KEY",
            color="green" if HAS_CHATGPT_KEY else "red",
            variant="light",
            size="sm",
        )
    )
    items.append(
        dmc.Badge(
            "Gemini: ready"
            if HAS_GEMINI_KEY
            else "Gemini: missing GEMINI_API_KEY",
            color="green" if HAS_GEMINI_KEY else "red",
            variant="light",
            size="sm",
        )
    )
    # The "unverified" badge cannot be decided here: knowing whether the
    # model list was checked means asking the provider, and this function runs
    # at page-import time. The slot is filled by `_sync_models` on first
    # render instead.
    items.append(html.Div(id="ai-model-check"))
    return dmc.Group(items, gap="xs")


component = dmc.Stack(
    gap="md",
    children=[
        _provider_status(),
        dmc.Paper(
            withBorder=True,
            p="md",
            children=dmc.Stack(
                gap="sm",
                children=[
                    dmc.Grid(
                        gutter="md",
                        children=[
                            dmc.GridCol(
                                dmc.Select(
                                    id="ai-provider",
                                    label="Provider",
                                    data=[
                                        {"value": "claude", "label": "Claude"},
                                        {"value": "chatgpt", "label": "ChatGPT"},
                                        {"value": "gemini", "label": "Gemini"},
                                    ],
                                    # Land on a provider whose key is present,
                                    # so the first click can succeed. Falls
                                    # back to Claude, which then reports the
                                    # missing key by name.
                                    value=(
                                        "claude"
                                        if HAS_CLAUDE_KEY
                                        else "chatgpt"
                                        if HAS_CHATGPT_KEY
                                        else "gemini"
                                        if HAS_GEMINI_KEY
                                        else "claude"
                                    ),
                                ),
                                span={"base": 12, "sm": 3},
                            ),
                            dmc.GridCol(
                                dmc.Select(
                                    id="ai-model",
                                    label="Model",
                                    # Filled by `_sync_models` on first
                                    # render — see offered_claude_models().
                                    data=[],
                                    value=None,
                                ),
                                span={"base": 12, "sm": 4},
                            ),
                            dmc.GridCol(
                                dmc.Select(
                                    id="ai-effort",
                                    label="Effort",
                                    description="Thinking depth",
                                    data=EFFORT_LEVELS,
                                    value=CLAUDE_EFFORT.get(
                                        CLAUDE_MODELS[0]["value"]
                                    ) or "low",
                                ),
                                span={"base": 6, "sm": 2},
                            ),
                            dmc.GridCol(
                                dmc.NumberInput(
                                    id="ai-max-tokens",
                                    label="Max tokens",
                                    description="Caps thinking + output together",
                                    value=CLAUDE_MAX_TOKENS[
                                        CLAUDE_MODELS[0]["value"]
                                    ],
                                    min=1000,
                                    max=128000,
                                    step=4000,
                                ),
                                span={"base": 6, "sm": 2},
                            ),
                            dmc.GridCol(
                                dmc.NumberInput(
                                    id="ai-seed",
                                    label="Seed",
                                    description="Bump for a fresh id namespace",
                                    value=1,
                                    min=1,
                                ),
                                span={"base": 12, "sm": 1},
                            ),
                        ],
                    ),
                    # What this run will cost, BEFORE it is triggered. The
                    # three controls above are all cost levers and none of
                    # them says so on its own — model sets the rate, max
                    # tokens sets the ceiling, effort sets how much of that
                    # ceiling gets used.
                    dmc.Alert(
                        id="ai-estimate",
                        color="gray",
                        variant="light",
                        p="xs",
                    ),
                    dmc.Textarea(
                        id="ai-prompt",
                        label="Prompt",
                        placeholder="E.g. 'a flowchart for onboarding a new engineer: signup → security training → first PR → mentorship pairing'",
                        autosize=True,
                        minRows=3,
                        maxRows=6,
                    ),
                    dmc.Group(
                        [
                            dmc.Button(
                                "Generate",
                                id="ai-generate-btn",
                                leftSection="✨",
                                color="indigo",
                                loaderProps={"type": "dots"},
                            ),
                            dmc.Button(
                                "Clear canvas",
                                id="ai-clear-btn",
                                variant="subtle",
                                color="red",
                            ),
                        ]
                    ),
                ],
            ),
        ),
        # Processing banner — driven by the callback's `running=` clause so
        # feedback appears the instant the click registers, not once the
        # model has returned. `running` collides with normal Outputs, so
        # this element is only *shown*/*hidden* from running; its inner
        # copy is static.
        html.Div(
            id="ai-processing-banner",
            style={"display": "none"},
            children=dmc.Alert(
                color="blue",
                variant="light",
                children=dmc.Group(
                    gap="sm",
                    children=[
                        dmc.Loader(size="sm", color="blue", type="bars"),
                        dmc.Stack(
                            gap=0,
                            children=[
                                dmc.Text(
                                    "Generating scene…",
                                    fw=600,
                                    size="sm",
                                ),
                                dmc.Text(
                                    "Sending prompt to the model and parsing "
                                    "the response — typically 2–20 s. Opus / "
                                    "Gemini Pro are slower than Sonnet / Flash.",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                        ),
                    ],
                ),
            ),
        ),
        dmc.Alert(
            id="ai-status",
            children="Ready.",
            color="gray",
            variant="light",
            title="Status",
        ),
        dcc.Store(id="ai-last-raw", data=""),
        # The streaming pair. `ai-run` holds the id of the generation in
        # flight plus how many elements the canvas has already been shown;
        # `ai-stream-tick` collects whatever arrived since. 400ms is fast
        # enough that shapes appear to land as they are drawn, and slow
        # enough that a long generation is a few dozen polls rather than a
        # few thousand.
        dcc.Store(id="ai-run", data=None),
        dcc.Interval(id="ai-stream-tick", interval=400, disabled=True),
        dmc.Tabs(
            value="canvas",
            children=[
                dmc.TabsList(
                    [
                        dmc.TabsTab("Canvas", value="canvas"),
                        dmc.TabsTab("Raw response", value="raw"),
                        dmc.TabsTab("Parsed envelope", value="parsed"),
                    ]
                ),
                dmc.TabsPanel(
                    value="canvas",
                    pt="sm",
                    children=dmc.Box(
                        style={"position": "relative"},
                        children=[
                            dmc.LoadingOverlay(
                                id="ai-canvas-overlay",
                                visible=False,
                                zIndex=100,
                                overlayProps={
                                    "radius": "md",
                                    "blur": 2,
                                    "backgroundOpacity": 0.55,
                                },
                                loaderProps={
                                    "color": "indigo",
                                    "type": "bars",
                                    "size": "lg",
                                },
                            ),
                            canvas_frame(
                                DashExcalidraw(
                                    id="ai-canvas",
                                    height="640px",
                                    UIOptions={
                                        "welcomeScreen": False,
                                        "canvasActions": {
                                            "clearCanvas": True,
                                            "export": False,
                                            "saveAsImage": True,
                                        },
                                    },
                                ),
                                min_height=640,
                            ),
                        ],
                    ),
                ),
                dmc.TabsPanel(
                    value="raw",
                    pt="sm",
                    children=dcc.Loading(
                        id="ai-raw-loading",
                        type="default",
                        delay_show=200,
                        delay_hide=300,
                        custom_spinner=dmc.Stack(
                            gap="xs",
                            p="sm",
                            children=[
                                dmc.Skeleton(height=18, width="40%", radius="sm"),
                                dmc.Skeleton(height=14, radius="sm"),
                                dmc.Skeleton(height=14, width="95%", radius="sm"),
                                dmc.Skeleton(height=14, width="80%", radius="sm"),
                                dmc.Skeleton(height=14, width="90%", radius="sm"),
                                dmc.Skeleton(height=14, width="70%", radius="sm"),
                                dmc.Skeleton(height=14, radius="sm"),
                                dmc.Skeleton(height=14, width="60%", radius="sm"),
                            ],
                        ),
                        children=dmc.ScrollArea(
                            style={"height": 520},
                            children=dmc.Code(
                                id="ai-raw",
                                block=True,
                                style={
                                    "whiteSpace": "pre-wrap",
                                    "wordBreak": "break-word",
                                    "fontSize": 11,
                                },
                            ),
                        ),
                    ),
                ),
                dmc.TabsPanel(
                    value="parsed",
                    pt="sm",
                    children=dcc.Loading(
                        id="ai-parsed-loading",
                        type="default",
                        delay_show=200,
                        delay_hide=300,
                        custom_spinner=dmc.Stack(
                            gap="xs",
                            p="sm",
                            children=[
                                dmc.Skeleton(height=18, width="35%", radius="sm"),
                                dmc.Skeleton(height=14, radius="sm"),
                                dmc.Skeleton(height=14, width="88%", radius="sm"),
                                dmc.Skeleton(height=14, width="92%", radius="sm"),
                                dmc.Skeleton(height=14, width="75%", radius="sm"),
                                dmc.Skeleton(height=14, radius="sm"),
                                dmc.Skeleton(height=14, width="65%", radius="sm"),
                            ],
                        ),
                        children=dmc.ScrollArea(
                            style={"height": 520},
                            children=dmc.Code(
                                id="ai-parsed",
                                block=True,
                                style={
                                    "whiteSpace": "pre-wrap",
                                    "wordBreak": "break-word",
                                    "fontSize": 11,
                                },
                            ),
                        ),
                    ),
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


@callback(
    Output("ai-estimate", "children"),
    Output("ai-estimate", "color"),
    Input("ai-provider", "value"),
    Input("ai-model", "value"),
    Input("ai-effort", "value"),
    Input("ai-max-tokens", "value"),
)
def _show_estimate(provider, model, effort, max_tokens):
    """Price this run before it happens.

    Two numbers, not one, and the reason is in `estimate_cost`: `max_tokens`
    is a ceiling, so a single figure has to choose between being pessimistic
    (quote the ceiling, and every real run looks like a bargain) or optimistic
    (quote the typical, and the bill can exceed the quote). Showing both makes
    the spread itself the information — it is exactly what effort controls.
    """
    if not model:
        # First paint: the model control ships empty and `_sync_models` fills
        # it. Without this the estimate would flash "no price on file for
        # this model", which reads as a broken model rather than an unfinished
        # render.
        return "Checking which models this key can call…", "gray"

    if provider == "gemini":
        # Gemini has no entry in MODEL_PRICING and its billing is not ours to
        # quote. Saying so beats rendering $0.00, which reads as "free".
        return "No cost estimate for Gemini here — see Google's pricing.", "gray"

    est = estimate_cost(model, effort, max_tokens)
    if not est["priced"]:
        if est["reason"] == "budget":
            # Mid-edit the NumberInput hands over whatever is in the box, so
            # this is a normal transient state, not an error worth shouting
            # about. It used to raise here and 500 the callback.
            return "Set a max-token budget to see the cost.", "gray"
        return "No price on file for this model — cost unknown.", "gray"

    # The budget AS PRICED, not the raw control value — they differ whenever
    # the box holds something like "64.000" or a number outside the range.
    budget = est["budget"]
    sent = est["effort"]
    effort_phrase = (
        f"effort {sent}" if sent else "no effort set (the model's own default)"
    )

    parts = [
        dmc.Text(
            [
                "About ",
                dmc.Text(format_money(est["typical"]), fw=700, span=True),
                f" for this run · at most {format_money(est['ceiling'])} "
                f"if it uses the whole budget.",
            ],
            size="sm",
        ),
        dmc.Text(
            f"{budget:,} max tokens · {effort_phrase} · "
            f"typical run uses ~{est['fraction']:.0%} of the budget.",
            size="xs",
            c="dimmed",
        ),
    ]

    # Say it out loud when the level in the selector is not the level that
    # will be sent — otherwise the estimate looks wrong rather than the
    # control looking inert.
    if effort and effort != "none" and sent is None:
        parts.append(
            dmc.Text(
                f"This model ignores the effort parameter, so “{effort}” "
                f"costs the same as any other level here.",
                size="xs",
                c="dimmed",
                fs="italic",
            )
        )

    return dmc.Stack(parts, gap=2), "gray"


# Clear stays SYNCHRONOUS and is its own callback. It is instant, and routing
# it through a job queue would add a round trip to a button whose whole value
# is that it responds immediately. Splitting it also keeps `ctx.triggered_id`
# out of the background worker, where callback context is a different animal.
#
# It writes the same Output as the generator, so one of the two must declare
# allow_duplicate — this one, because it is the secondary writer.
@callback(
    Output("ai-model", "data"),
    Output("ai-model", "value"),
    Output("ai-model-check", "children"),
    Input("ai-provider", "value"),
    prevent_initial_call=False,
)
def _sync_models(provider):
    """Fill the model list, and say whether it was verified.

    `prevent_initial_call=False` is load-bearing: this fires on first render,
    which is what lets the control ship empty and the availability check stay
    off the import path.
    """
    if provider == "chatgpt":
        return OPENAI_MODELS, OPENAI_MODELS[0]["value"], None
    if provider == "gemini":
        return GEMINI_MODELS, GEMINI_MODELS[0]["value"], None

    data, verified = offered_claude_models()
    badge = (
        None
        if verified
        else dmc.Badge(
            "model list unverified", color="yellow", variant="light", size="sm"
        )
    )
    return data, data[0]["value"], badge


@callback(
    Output("ai-effort", "value"),
    Output("ai-effort", "data"),
    Output("ai-max-tokens", "value"),
    Output("ai-effort", "disabled", allow_duplicate=True),
    Input("ai-model", "value"),
    prevent_initial_call=True,
)
def _sync_model_defaults(model):
    """Move effort and budget to this model's defaults when the model changes.

    Without this, switching models silently carries the previous model's
    settings over — which quietly invalidates a comparison, because you would
    be reading a difference between models that is partly a difference in
    configuration. The effort control is also disabled outright on models that
    reject the parameter, so the UI cannot offer a choice the API will 400 on.
    """
    capable = model in EFFORT_CAPABLE
    allowed = set(supported_efforts(model))
    data = [e for e in EFFORT_LEVELS if e["value"] in allowed]
    # MODEL_* rather than CLAUDE_*: switching to a ChatGPT model has to pick
    # up ITS defaults, or the run would carry the previous provider's budget
    # and the comparison would be measuring configuration, not models.
    effort = (MODEL_EFFORT.get(model) or "none") if capable else "none"
    if effort not in allowed:
        effort = "none"
    return effort, data, MODEL_MAX_TOKENS.get(model, 32000), not capable


# Clear stays SYNCHRONOUS and is its own callback. It is instant, and routing
# it through a job queue would add a round trip to a button whose whole value
# is that it responds immediately. Splitting it also keeps `ctx.triggered_id`
# out of the background worker, where callback context is a different animal.
#
# It writes the same Output as the generator, so one of the two must declare
# allow_duplicate — this one, because it is the secondary writer.
@callback(
    Output("ai-canvas", "command", allow_duplicate=True),
    Output("ai-status", "children", allow_duplicate=True),
    Output("ai-status", "color", allow_duplicate=True),
    Output("ai-raw", "children", allow_duplicate=True),
    Output("ai-parsed", "children", allow_duplicate=True),
    Output("ai-last-raw", "data", allow_duplicate=True),
    Input("ai-clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _clear(_clicks):
    cmd = {
        "id": f"clear-{uuid.uuid4()}",
        "type": "updateScene",
        "payload": {"elements": []},
    }
    return cmd, "Canvas cleared.", "gray", "", "", ""


@callback(
    Output("ai-canvas", "command"),
    Output("ai-status", "children"),
    Output("ai-status", "color"),
    Output("ai-raw", "children"),
    Output("ai-parsed", "children"),
    Output("ai-last-raw", "data"),
    Output("ai-run", "data"),
    Output("ai-stream-tick", "disabled"),
    Input("ai-generate-btn", "n_clicks"),
    State("ai-provider", "value"),
    State("ai-model", "value"),
    State("ai-effort", "value"),
    State("ai-max-tokens", "value"),
    State("ai-prompt", "value"),
    running=[
        # ONLY the banner. The canvas overlay used to be here and is gone on
        # purpose: it covered the canvas for the whole call, which is the
        # exact thing streaming exists to remove. Everything else that needs
        # locking is handled by `_lock_controls`, which keys off the ticker
        # and therefore stays on for the whole DRAWING, not just this
        # callback — which now returns in milliseconds.
        (
            Output("ai-processing-banner", "style"),
            {"display": "block", "marginTop": 4, "marginBottom": 4},
            {"display": "none"},
        ),
    ],
    prevent_initial_call=True,
)
def _generate(_gen_clicks, provider, model, effort, max_tokens, prompt):
    """START a generation. Returns immediately; the canvas fills in as it draws.

    This used to block for the whole call and hand back a finished scene, which
    is why the page had a loading overlay: there was nothing to show until
    there was everything to show. Claude and ChatGPT runs now go to a worker
    thread that parses elements out of the token stream as each one closes,
    and `ai-stream-tick` collects them — first shape on the canvas in a few
    seconds instead of a minute of spinner.

    `background=` is gone with the blocking call. It existed so a 100-second
    generation could not hold a request worker and take /healthz down with it;
    the generation no longer happens in a callback at all, so the risk it
    guarded against is gone with it. The producer is a plain thread — see
    lib/scene_stream.start for why not a background worker.

    Gemini still runs synchronously: `_call_gemini` has no streaming path and
    returns a whole string, so there is nothing to stream. It keeps the old
    behaviour rather than pretending otherwise.
    """
    idle = (no_update,) * 6 + (no_update, True)
    if not prompt or not prompt.strip():
        return (no_update, "Write a prompt first.", "yellow") + idle[3:]

    # ---- THE SPEND GATE -------------------------------------------------
    # This check has to live HERE, not on the page's `tier: auth`, and the
    # reason is worth stating because the frontmatter looks like it covers it.
    #
    #  1. `lib/page_tiers.degraded_tier` makes every tier except `hidden` fail
    #     OPEN when Clerk is not configured. That is the right trade for
    #     reading documentation and exactly the wrong one for a page that
    #     spends money, which must fail CLOSED.
    #  2. Page tiers are path-based, and every Dash callback posts to the one
    #     shared `/_dash-update-component` route. No path-based gate can tell
    #     this callback from any other.
    #
    # So the page tier governs who can READ the page; this governs who can
    # make it BILL.
    if not _spend_allowed():
        return (
            no_update,
            "Sign in to generate — this page spends real API credits, so "
            "generation is limited to signed-in visitors.",
            "yellow",
        ) + idle[3:]

    missing = {
        "claude": (not HAS_CLAUDE_KEY, "ANTHROPIC_API_KEY is not set in the environment."),
        "chatgpt": (
            not HAS_CHATGPT_KEY,
            "CHATGPT_API_KEY / OPENAI_API_KEY is not set in the environment.",
        ),
        "gemini": (
            not HAS_GEMINI_KEY,
            "GEMINI_API_KEY / GOOGLE_API_KEY is not set in the environment.",
        ),
    }.get(provider, (False, ""))
    if missing[0]:
        return (no_update, missing[1], "red") + idle[3:]

    # ---- Gemini: no stream available, so keep the one-shot path ------------
    if provider == "gemini":
        started = time.monotonic()
        try:
            raw = _call_gemini(model, prompt.strip())
        except Exception as exc:  # noqa: BLE001 - surface any provider error
            traceback.print_exc()
            return (no_update, f"{provider} call failed: {exc}", "red",
                    str(exc), "", "", no_update, True)
        try:
            parsed = _parse_and_normalize(raw)
        except json.JSONDecodeError as exc:
            return (
                no_update,
                f"Parse error at char {exc.pos}: {exc.msg}. See Parsed tab for context.",
                "red", raw, _format_parse_error(raw, exc), raw, no_update, True,
            )
        except ValueError as exc:
            return (no_update, f"Parse error: {exc}", "red", raw, str(exc), raw,
                    no_update, True)

        elements = parsed.get("elements", [])
        cmd = {
            "id": f"ai-{uuid.uuid4()}",
            "type": "updateScene",
            "payload": {
                "elements": elements,
                "appState": parsed.get("appState", {}),
                "files": parsed.get("files", {}),
            },
        }
        status = _benchmark_status(
            provider, model, len(elements), time.monotonic() - started, None
        )
        return (cmd, status, "green", raw, json.dumps(parsed, indent=2), raw,
                no_update, True)

    # ---- Claude / ChatGPT: stream it --------------------------------------
    try:
        run_id = scene_stream.start(
            model=model,
            user_prompt=prompt.strip(),
            max_tokens=max_tokens,
            effort=effort,
        )
    except Exception as exc:  # noqa: BLE001 - a bad model id, a missing key
        traceback.print_exc()
        return (no_update, f"{type(exc).__name__}: {exc}", "red") + idle[3:]

    # Blank the canvas so the drawing starts from nothing and each shape's
    # arrival is visible, rather than accumulating over the previous scene.
    return (
        {"id": f"ai-reset-{run_id[:8]}", "type": "resetScene", "payload": {}},
        "Drawing…",
        "gray",
        no_update,
        no_update,
        no_update,
        {"id": run_id, "cursor": 0, "provider": provider, "model": model},
        False,
    )


@callback(
    Output("ai-canvas", "command", allow_duplicate=True),
    Output("ai-status", "children", allow_duplicate=True),
    Output("ai-status", "color", allow_duplicate=True),
    Output("ai-raw", "children", allow_duplicate=True),
    Output("ai-parsed", "children", allow_duplicate=True),
    Output("ai-last-raw", "data", allow_duplicate=True),
    Output("ai-run", "data", allow_duplicate=True),
    Output("ai-stream-tick", "disabled", allow_duplicate=True),
    Input("ai-stream-tick", "n_intervals"),
    State("ai-run", "data"),
    prevent_initial_call=True,
)
def _stream_tick(_n, run):
    """Collect whatever the worker has parsed since the last poll."""
    stop = (no_update,) * 7 + (True,)
    if not run or not run.get("id"):
        return stop

    state = scene_stream.take(run["id"], run.get("cursor", 0))
    if not state["found"]:
        # Expired, forgotten, or an instance restart took the store with it.
        # Stop polling rather than ask forever about a run that cannot answer.
        return stop

    elements = state["all"]
    run_next = {**run, "cursor": state["cursor"]}

    if state["error"]:
        scene_stream.forget(run["id"])
        return (no_update, state["error"], "red", no_update, no_update,
                no_update, None, True)

    # updateScene REPLACES the scene, so every tick sends everything so far.
    # captureUpdate NEVER while drawing: without it each tick becomes its own
    # undo step, and a 40-element scene would take 40 Ctrl+Z to undo.
    cmd = no_update
    if state["elements"]:
        cmd = {
            "id": f"ai-tick-{run['id'][:8]}-{state['cursor']}",
            "type": "updateScene",
            "payload": {"elements": elements, "captureUpdate": "NEVER"},
        }

    if not state["done"]:
        plural = "s" if len(elements) != 1 else ""
        return (
            cmd,
            f"Drawing… {len(elements)} element{plural} so far "
            f"({state['elapsed']:.0f}s)",
            "gray",
            no_update, no_update, no_update, run_next, False,
        )

    scene_stream.forget(run["id"])
    if not elements:
        return (
            no_update,
            "The model returned no elements. Try a different model or a "
            "larger budget.",
            "yellow",
            no_update, no_update, no_update, None, True,
        )

    # One last updateScene, this time as a single undoable step.
    final_cmd = {
        "id": f"ai-final-{run['id'][:8]}",
        "type": "updateScene",
        "payload": {"elements": elements, "captureUpdate": "IMMEDIATELY"},
    }
    # The Raw tab shows the scene REBUILT from the streamed elements rather
    # than the exact bytes off the wire: the parser consumes the deltas as
    # they arrive, and keeping a second full copy of every response in memory
    # to populate a tab is not worth the memory.
    rebuilt = json.dumps({"elements": elements}, indent=2)
    status = _benchmark_status(
        run.get("provider"), run.get("model"), len(elements),
        state["elapsed"], state["meta"],
    )
    return final_cmd, status, "green", rebuilt, rebuilt, rebuilt, None, True


@callback(
    Output("ai-generate-btn", "loading"),
    Output("ai-generate-btn", "disabled"),
    Output("ai-clear-btn", "disabled"),
    Output("ai-prompt", "disabled"),
    Output("ai-provider", "disabled"),
    Output("ai-model", "disabled"),
    Output("ai-max-tokens", "disabled"),
    Input("ai-stream-tick", "disabled"),
)
def _lock_controls(tick_disabled):
    """Lock the controls while a drawing is in flight.

    Keyed on the TICKER, not on the generate callback's lifetime: that
    callback now returns in milliseconds, so a `running=` lock would release
    while the canvas was still filling in. The ticker being enabled is the
    definition of "a run is in progress".
    """
    drawing = not tick_disabled
    return (drawing,) * 7
