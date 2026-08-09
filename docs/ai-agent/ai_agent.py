"""AI agent: turn a prompt into an Excalidraw scene via Claude or Gemini.

Uses the command dispatch pattern (`command: updateScene`) — no component
remount, no key-hack needed on the canvas. The same page compares Claude
Opus 4.7 / Sonnet 4.6 against Gemini 2.5 Flash / Pro side by side.

Ship-readiness checklist for using this in your own production app:

1. Set env vars:
     ANTHROPIC_API_KEY=...
     GEMINI_API_KEY=...
   Either is optional — the page disables the corresponding provider if
   the key is missing.

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
from lib import background as _background
from lib.scene_ai import (  # shared with /benchmark — see lib/scene_ai.py
    CLAUDE_EFFORT,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODELS,
    CLAUDE_PRICING,
    EFFORT_CAPABLE,
    EFFORT_LEVELS,
    GEMINI_MAX_TOKENS,
    GEMINI_MODELS,
    SYSTEM_PROMPT,
    _call_claude,
    _call_gemini,
    _cleanup_json,
    _coerce_types,
    _extract_json_block,
    _parse_and_normalize,
    _spend_allowed,
)
from docs._shared import canvas_frame, sync_canvas_theme

sync_canvas_theme("ai-canvas")

# ---------------------------------------------------------------------------
# Prompt template (domain-specific instructions for producing Excalidraw JSON)
# ---------------------------------------------------------------------------

HAS_CLAUDE_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
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
            "Gemini: ready"
            if HAS_GEMINI_KEY
            else "Gemini: missing GEMINI_API_KEY",
            color="green" if HAS_GEMINI_KEY else "red",
            variant="light",
            size="sm",
        )
    )
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
                                        {"value": "gemini", "label": "Gemini"},
                                    ],
                                    value=(
                                        "claude"
                                        if HAS_CLAUDE_KEY
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
                                    data=CLAUDE_MODELS,
                                    value=CLAUDE_MODELS[0]["value"],
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
                                    value=CLAUDE_MAX_TOKENS[CLAUDE_MODELS[0]["value"]],
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
    Output("ai-model", "data"),
    Output("ai-model", "value"),
    Input("ai-provider", "value"),
    prevent_initial_call=False,
)
def _sync_models(provider):
    data = CLAUDE_MODELS if provider == "claude" else GEMINI_MODELS
    return data, data[0]["value"]


@callback(
    Output("ai-effort", "value"),
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
    effort = (CLAUDE_EFFORT.get(model) or "none") if capable else "none"
    return effort, CLAUDE_MAX_TOKENS.get(model, 32000), not capable


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
    Input("ai-generate-btn", "n_clicks"),
    State("ai-provider", "value"),
    State("ai-model", "value"),
    State("ai-effort", "value"),
    State("ai-max-tokens", "value"),
    State("ai-prompt", "value"),
    running=[
        # Flip these on for the duration of the callback, off when it
        # finishes — gives the user immediate feedback without needing a
        # second callback round trip.
        (Output("ai-generate-btn", "loading"), True, False),
        (Output("ai-generate-btn", "disabled"), True, False),
        (Output("ai-clear-btn", "disabled"), True, False),
        (Output("ai-prompt", "disabled"), True, False),
        (Output("ai-provider", "disabled"), True, False),
        (Output("ai-model", "disabled"), True, False),
        (Output("ai-effort", "disabled"), True, False),
        (Output("ai-max-tokens", "disabled"), True, False),
        (
            Output("ai-processing-banner", "style"),
            {"display": "block", "marginTop": 4, "marginBottom": 4},
            {"display": "none"},
        ),
        (Output("ai-canvas-overlay", "visible"), True, False),
    ],
    prevent_initial_call=True,
    # Runs in a separate process when a manager is configured, so a 100-second
    # generation does not hold a request worker and take the rest of the site
    # — /healthz included — down with it. Falls back to a synchronous callback
    # when no manager is available, so the page still works on a bare install.
    background=_background.enabled(),
)
def _generate(_gen_clicks, provider, model, effort, max_tokens, prompt):
    if not prompt or not prompt.strip():
        return no_update, "Write a prompt first.", "yellow", no_update, no_update, no_update

    # ---- THE SPEND GATE -------------------------------------------------
    # This check has to live HERE, not on the page's `tier: auth`, and the
    # reason is worth stating because the frontmatter looks like it covers it.
    #
    # Two gaps, both by design upstream:
    #
    #  1. `lib/page_tiers.degraded_tier` makes every tier except `hidden`
    #     fail OPEN when Clerk is not configured. That is the right trade for
    #     reading documentation — a misconfigured deploy should not hide the
    #     docs — and exactly the wrong one for a page that spends money, which
    #     must fail CLOSED.
    #  2. Page tiers are path-based, and every Dash callback in the app posts
    #     to the single shared `/_dash-update-component` route. No path-based
    #     gate can tell this callback from any other, so even a correctly
    #     configured tier never sees the request that does the spending.
    #
    # So the page tier governs who can READ the page; this governs who can
    # make it BILL. Anonymous callers get told what to do rather than a bare
    # denial, because on a public docs site most of them are just curious.
    if not _spend_allowed():
        return (
            no_update,
            "Sign in to generate — this page spends real API credits, so "
            "generation is limited to signed-in visitors.",
            "yellow",
            no_update,
            no_update,
            no_update,
        )

    if provider == "claude" and not HAS_CLAUDE_KEY:
        return (
            no_update,
            "ANTHROPIC_API_KEY is not set in the environment.",
            "red",
            no_update,
            no_update,
            no_update,
        )
    if provider == "gemini" and not HAS_GEMINI_KEY:
        return (
            no_update,
            "GEMINI_API_KEY / GOOGLE_API_KEY is not set in the environment.",
            "red",
            no_update,
            no_update,
            no_update,
        )

    started = time.monotonic()
    try:
        if provider == "claude":
            raw, meta = _call_claude(model, prompt.strip(), max_tokens, effort)
        else:
            raw, meta = _call_gemini(model, prompt.strip()), None
    except Exception as exc:  # noqa: BLE001 - surface any provider error
        traceback.print_exc()
        return (
            no_update,
            f"{provider} call failed: {exc}",
            "red",
            str(exc),
            "",
            "",
        )

    try:
        parsed = _parse_and_normalize(raw)
    except json.JSONDecodeError as exc:
        return (
            no_update,
            f"Parse error at char {exc.pos}: {exc.msg}. See Parsed tab for context.",
            "red",
            raw,
            _format_parse_error(raw, exc),
            raw,
        )
    except ValueError as exc:
        return (
            no_update,
            f"Parse error: {exc}",
            "red",
            raw,
            str(exc),
            raw,
        )

    pretty_raw = raw
    pretty_parsed = json.dumps(parsed, indent=2)
    element_count = len(parsed.get("elements", []))
    cmd = {
        "id": f"ai-{uuid.uuid4()}",
        "type": "updateScene",
        "payload": {
            "elements": parsed.get("elements", []),
            "appState": parsed.get("appState", {}),
            "files": parsed.get("files", {}),
        },
    }
    # Elapsed time is in the status on purpose. Generation on a thinking
    # model can legitimately take a minute or more, and a bare spinner gives
    # the reader no way to tell a slow run from a broken one — which is
    # exactly how a 473-second run got reported as a hang.
    elapsed = time.monotonic() - started
    status = _benchmark_status(provider, model, element_count, elapsed, meta)
    return cmd, status, "green", pretty_raw, pretty_parsed, raw