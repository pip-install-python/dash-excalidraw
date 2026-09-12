"""Upload a reference image and ask a model to redraw it in Excalidraw.

The /ai-agent page starts from a sentence. This one starts from a picture, and
the interesting part is the constraint: Excalidraw has six primitives, so the
model cannot reproduce a photograph — it has to decide what the image IS and
rebuild that. A screenshot of a flowchart comes back as a flowchart; a photo of
a cat comes back as a disappointment. That gap is the point of the example.

DELIBERATELY LIMITED
- One image, one model, one drawing. Cross-model tracing belongs on
  /benchmark's model axis if it is ever wanted; here a second variant would
  double the bill for a page whose job is to show the mechanism.
- Synchronous, like /benchmark. The generate path on /ai-agent runs through a
  background job queue; that machinery earns its place there and would be
  noise here.
- Claude and ChatGPT only. Both take an image through the same `call_model`
  signature and report the same meta; Gemini's client takes neither a budget
  nor an effort, so a cost and a matched setting could not be shown.
"""

from __future__ import annotations

import base64
import binascii
import io
import os
import time

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame, sync_canvas_theme
from lib import scene_stream, spend
from lib.scene_ai import (
    COMPARABLE_MODELS,
    EFFORT_LEVELS,
    MODEL_EFFORT,
    MODEL_LABEL,
    MODEL_MAX_TOKENS,
    MODEL_PRICING,
    NO_KEYS_NOTICE,
    PROVIDER_OF,
    TRACE_SYSTEM_PROMPT,
    VISION_MODELS,
    _spend_allowed,
    any_provider_configured,
    estimate_cost,
    format_money,
    image_input_tokens,
    supported_efforts,
)

sync_canvas_theme("trace-canvas")

# Only models that can actually see the image. VISION_MODELS was measured
# rather than assumed — see lib/scene_ai.py.
TRACE_MODELS = [m for m in COMPARABLE_MODELS if m["value"] in VISION_MODELS]

# Anthropic rejects images over 5 MB and OpenAI has its own ceiling; browsers
# will happily hand over a 12 MB phone photo. Refusing early beats a provider
# error several frames away, and the number is in bytes of DECODED image.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

ACCEPTED = {"image/png", "image/jpeg", "image/gif", "image/webp"}

ANY_KEY = any_provider_configured()

HAS_CLAUDE_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
HAS_CHATGPT_KEY = bool(os.environ.get("CHATGPT_API_KEY")) or bool(
    os.environ.get("OPENAI_API_KEY")
)


def _decode_upload(contents: str) -> tuple[str, str, int, int, int]:
    """`(media_type, b64, byte_size, width, height)` from a dcc.Upload value.

    dcc.Upload hands over a data URL. Everything downstream needs the media
    type and the payload separately, and the dimensions are what make the
    image's share of the bill estimable instead of invisible.
    """
    if not contents or "," not in contents:
        raise ValueError("No image data in the upload.")
    header, payload = contents.split(",", 1)
    media_type = header.split(";")[0].removeprefix("data:") or ""
    if media_type not in ACCEPTED:
        raise ValueError(
            f"{media_type or 'that file'} is not an image the APIs accept. "
            f"Use PNG, JPEG, GIF or WebP."
        )
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("That upload is not valid base64 image data.") from exc
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError(
            f"Image is {len(raw) / 1024 / 1024:.1f} MB; the limit here is "
            f"{MAX_IMAGE_BYTES // 1024 // 1024} MB. Scale it down and retry."
        )
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as im:
            width, height = im.size
    except Exception:  # noqa: BLE001 - dimensions are a nicety, not a gate
        width = height = 0
    return media_type, payload, len(raw), width, height


component = dmc.Stack(
    gap="md",
    children=[
        # Exactly one of these two shows. Which one depends on whether this
        # deployment can call anything at all — a spend warning on a site that
        # cannot spend is as misleading as a missing one on a site that can.
        dmc.Alert(
            NO_KEYS_NOTICE,
            title="AI generation is disabled on this site",
            color="blue",
            variant="light",
            style={} if not ANY_KEY else {"display": "none"},
        ),
        dmc.Alert(
            title="This page spends real API credits",
            color="yellow",
            style={"display": "none"} if not ANY_KEY else {},
            children=(
                "Tracing sends your image and a long instruction to a paid "
                "model. The estimate below includes the image's own input "
                "tokens — check it before running."
            ),
        ),
        dmc.Paper(
            withBorder=True,
            p="md",
            children=dmc.Stack(
                gap="sm",
                children=[
                    dcc.Upload(
                        id="trace-upload",
                        multiple=False,
                        accept="image/*",
                        children=dmc.Paper(
                            withBorder=True,
                            p="xl",
                            radius="md",
                            style={
                                "borderStyle": "dashed",
                                "cursor": "pointer",
                                "textAlign": "center",
                            },
                            children=dmc.Stack(
                                gap=4,
                                align="center",
                                children=[
                                    dmc.Text(
                                        "Drop a reference image here, or click "
                                        "to choose one",
                                        fw=600,
                                    ),
                                    dmc.Text(
                                        "PNG, JPEG, GIF or WebP · up to 4 MB · "
                                        "diagrams and screenshots trace far "
                                        "better than photographs",
                                        size="xs",
                                        c="dimmed",
                                    ),
                                ],
                            ),
                        ),
                    ),
                    html.Div(id="trace-preview"),
                    dmc.Grid(
                        gutter="md",
                        children=[
                            dmc.GridCol(
                                dmc.Select(
                                    id="trace-model",
                                    label="Model",
                                    description="Only models that accept images",
                                    data=TRACE_MODELS,
                                    value=TRACE_MODELS[0]["value"],
                                ),
                                span={"base": 12, "sm": 5},
                            ),
                            dmc.GridCol(
                                dmc.Select(
                                    id="trace-effort",
                                    label="Effort",
                                    description="Thinking depth",
                                    data=EFFORT_LEVELS,
                                    value=MODEL_EFFORT.get(TRACE_MODELS[0]["value"])
                                    or "low",
                                ),
                                span={"base": 6, "sm": 3},
                            ),
                            dmc.GridCol(
                                dmc.NumberInput(
                                    id="trace-max-tokens",
                                    label="Max tokens",
                                    description="Covers thinking + output",
                                    value=MODEL_MAX_TOKENS[TRACE_MODELS[0]["value"]],
                                    min=1000,
                                    max=128000,
                                    step=4000,
                                ),
                                span={"base": 6, "sm": 4},
                            ),
                        ],
                    ),
                    dmc.Textarea(
                        id="trace-note",
                        label="Extra instruction (optional)",
                        description=(
                            "Anything the image cannot say for itself — "
                            "'ignore the background', 'keep it monochrome'"
                        ),
                        autosize=True,
                        minRows=2,
                    ),
                    dmc.Alert(id="trace-estimate", color="gray", variant="light", p="xs"),
                    dmc.Group(
                        children=[
                            dmc.Button(
                                "Trace this image",
                                id="trace-run-btn",
                                color="indigo",
                                disabled=not ANY_KEY,
                            ),
                            # THE BRAKES. A trace sends an image on every
                            # run, so its input cost is higher than a prompt-
                            # only call and stopping early saves more.
                            dmc.Button(
                                "Stop",
                                id="trace-stop",
                                leftSection="■",
                                color="red",
                                disabled=True,
                            ),
                            dmc.Button(
                                "Clear",
                                id="trace-clear",
                                variant="subtle",
                                color="gray",
                            ),
                        ]
                    ),
                ],
            ),
        ),
        dmc.Alert(id="trace-status", color="gray", variant="light"),
        dmc.Grid(
            gutter="md",
            children=[
                dmc.GridCol(
                    dmc.Stack(
                        gap="xs",
                        children=[
                            dmc.Text("Reference", size="sm", fw=600, c="dimmed"),
                            html.Div(id="trace-reference"),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
                dmc.GridCol(
                    dmc.Stack(
                        gap="xs",
                        children=[
                            dmc.Text("Traced", size="sm", fw=600, c="dimmed"),
                            canvas_frame(
                                DashExcalidraw(
                                    id="trace-canvas",
                                    height="520px",
                                    # View mode: this is a specimen to compare
                                    # against the reference, not a canvas to
                                    # edit — and a stray click should not
                                    # change what you are comparing.
                                    viewModeEnabled=True,
                                ),
                                min_height=520,
                            ),
                        ],
                    ),
                    span={"base": 12, "md": 6},
                ),
            ],
        ),
        dcc.Store(id="trace-image-store"),
        # Streaming pair, same shape as /ai-agent: the run id plus how many
        # elements the canvas has already seen, and a ticker that collects
        # whatever arrived since.
        dcc.Store(id="trace-run", data=None),
        dcc.Interval(id="trace-tick", interval=400, disabled=True),
    ],
)


@callback(
    Output("trace-image-store", "data"),
    Output("trace-preview", "children"),
    Input("trace-upload", "contents"),
    State("trace-upload", "filename"),
    prevent_initial_call=True,
)
def _accept_upload(contents, filename):
    """Validate and describe the upload before a single credit is spent."""
    if not contents:
        return None, None
    try:
        media_type, b64, size, width, height = _decode_upload(contents)
    except ValueError as exc:
        return None, dmc.Alert(str(exc), color="red", variant="light")

    tokens = image_input_tokens(width, height)
    dims = f"{width}x{height}" if width else "dimensions unknown"
    return (
        {
            "media_type": media_type,
            "b64": b64,
            "width": width,
            "height": height,
            "tokens": tokens,
            "data_url": contents,
        },
        dmc.Group(
            gap="xs",
            children=[
                dmc.Badge(filename or "image", variant="light"),
                dmc.Badge(f"{size / 1024:.0f} KB", color="gray", variant="light"),
                dmc.Badge(dims, color="gray", variant="light"),
                dmc.Badge(f"~{tokens:,} input tokens", color="teal", variant="light"),
            ],
        ),
    )


@callback(
    Output("trace-effort", "value"),
    Output("trace-effort", "data"),
    Output("trace-max-tokens", "value"),
    Input("trace-model", "value"),
    prevent_initial_call=True,
)
def _sync_model_defaults(model):
    """Move effort and budget to the chosen model's defaults, and offer only
    the levels it accepts — Sonnet 4.6 rejects `xhigh`, and a selector that
    lists it is a 400 waiting to happen."""
    allowed = set(supported_efforts(model))
    data = [e for e in EFFORT_LEVELS if e["value"] in allowed]
    effort = MODEL_EFFORT.get(model) or "none"
    if effort not in allowed:
        effort = "none"
    return effort, data, MODEL_MAX_TOKENS.get(model, 24000)


@callback(
    Output("trace-estimate", "children"),
    Input("trace-model", "value"),
    Input("trace-effort", "value"),
    Input("trace-max-tokens", "value"),
    Input("trace-image-store", "data"),
)
def _show_estimate(model, effort, max_tokens, image):
    """Price the trace before it runs, image included."""
    image_tokens = (image or {}).get("tokens", 0)
    est = estimate_cost(model, effort, max_tokens, extra_input_tokens=image_tokens)
    if not est["priced"]:
        if est["reason"] == "budget":
            return "Set a max-token budget to see the cost."
        return "No price on file for this model — cost unknown."

    tail = (
        f"{est['budget']:,} max tokens · effort {est['effort'] or 'model default'}"
    )
    if image_tokens:
        tail += f" · image ~{image_tokens:,} input tokens"
    else:
        tail += " · no image yet, so this is the text-only cost"

    return dmc.Stack(
        gap=2,
        children=[
            dmc.Text(
                [
                    "About ",
                    dmc.Text(format_money(est["typical"]), fw=700, span=True),
                    f" · at most {format_money(est['ceiling'])} if it uses the "
                    f"whole budget.",
                ],
                size="sm",
            ),
            dmc.Text(tail, size="xs", c="dimmed"),
        ],
    )


@callback(
    Output("trace-canvas", "command", allow_duplicate=True),
    Output("trace-reference", "children", allow_duplicate=True),
    Output("trace-status", "children", allow_duplicate=True),
    Output("trace-status", "color", allow_duplicate=True),
    Input("trace-clear", "n_clicks"),
    prevent_initial_call=True,
)
def _clear(_clicks):
    """Synchronous and separate, for the same reason /ai-agent keeps its clear
    button out of the generate path: it is instant, and it must stay instant."""
    return (
        {"id": f"trace-clear-{time.time()}", "type": "resetScene", "payload": {}},
        None,
        "Cleared.",
        "gray",
    )


@callback(
    Output("trace-canvas", "command"),
    Output("trace-reference", "children"),
    Output("trace-status", "children"),
    Output("trace-status", "color"),
    Output("trace-run", "data"),
    Output("trace-tick", "disabled"),
    Input("trace-run-btn", "n_clicks"),
    State("trace-model", "value"),
    State("trace-effort", "value"),
    State("trace-max-tokens", "value"),
    State("trace-note", "value"),
    State("trace-image-store", "data"),
    prevent_initial_call=True,
)
def _trace(_clicks, model, effort, max_tokens, note, image):
    """START a trace. The canvas fills in as the model draws.

    Same shape as /ai-agent: this returns in milliseconds and `trace-tick`
    does the collecting, so the reference appears immediately and the drawing
    builds up beside it instead of arriving whole after a minute of spinner.
    """
    if not image:
        return no_update, no_update, "Upload a reference image first.", "yellow", None, True

    # The button is disabled without a key, so this is only reachable by a
    # crafted request. Answered in the same words and colour as the page's
    # own notice — a caller here has not done anything wrong.
    if not ANY_KEY:
        return no_update, no_update, NO_KEYS_NOTICE, "blue", None, True

    if not _spend_allowed():
        return (
            no_update, no_update,
            "Sign in to trace an image — this page spends real API credits.",
            "yellow", None, True,
        )

    provider = PROVIDER_OF.get(model)
    if provider == "claude" and not HAS_CLAUDE_KEY:
        return no_update, no_update, "ANTHROPIC_API_KEY is not set.", "red", None, True
    if provider == "chatgpt" and not HAS_CHATGPT_KEY:
        return no_update, no_update, "CHATGPT_API_KEY is not set.", "red", None, True

    prompt = (
        "Trace the attached reference image as an Excalidraw scene."
        + (f"\n\nAdditional instruction: {note.strip()}" if note and note.strip() else "")
    )

    # The ceiling, up front. `stream_model` admits once per run too, but it is
    # a generator: its body does not run until the worker advances it, so
    # without this the refusal would arrive as a red error on a run that had
    # already been created. A trace also carries the image's input tokens, so
    # it is priced with them rather than as a bare prompt.
    try:
        spend.check(
            estimate_cost(
                model, effort, max_tokens,
                extra_input_tokens=image_input_tokens(
                    image.get("width") or 0, image.get("height") or 0
                ),
            )["typical"]
        )
    except spend.CeilingReached as exc:
        return no_update, no_update, str(exc), "yellow", None, True

    try:
        run_id = scene_stream.start(
            model=model,
            user_prompt=prompt,
            max_tokens=max_tokens,
            effort=effort,
            image=(image["media_type"], image["b64"]),
            system=TRACE_SYSTEM_PROMPT,
        )
    except Exception as exc:  # noqa: BLE001
        return no_update, no_update, f"{type(exc).__name__}: {exc}", "red", None, True

    # Show the reference straight away — the comparison is the whole point, and
    # having it on screen while the trace builds is better than after.
    reference = dmc.Image(
        src=image["data_url"],
        radius="md",
        fit="contain",
        style={
            "maxHeight": "520px",
            "border": "1px solid var(--mantine-color-gray-3)",
        },
    )
    return (
        {"id": f"trace-reset-{run_id[:8]}", "type": "resetScene", "payload": {}},
        reference,
        "Tracing…",
        "gray",
        {"id": run_id, "model": model, "cursor": 0},
        False,
    )


@callback(
    Output("trace-canvas", "command", allow_duplicate=True),
    Output("trace-status", "children", allow_duplicate=True),
    Output("trace-status", "color", allow_duplicate=True),
    Output("trace-run", "data", allow_duplicate=True),
    Output("trace-tick", "disabled", allow_duplicate=True),
    Input("trace-tick", "n_intervals"),
    State("trace-run", "data"),
    prevent_initial_call=True,
)
def _trace_tick(_n, run):
    """Collect whatever the worker parsed since the last poll."""
    if not run or not run.get("id"):
        return no_update, no_update, no_update, no_update, True

    state = scene_stream.take(run["id"], run.get("cursor", 0))
    if not state["found"]:
        return no_update, no_update, no_update, None, True

    elements = state["all"]
    if state["error"]:
        scene_stream.forget(run["id"])
        return no_update, state["error"], "red", None, True

    # updateScene replaces the scene, so send everything so far. NEVER while
    # drawing keeps a 30-element trace from becoming 30 undo steps.
    cmd = no_update
    if state["elements"]:
        cmd = {
            "id": f"trace-tick-{run['id'][:8]}-{state['cursor']}",
            "type": "updateScene",
            "payload": {"elements": elements, "captureUpdate": "NEVER"},
        }
    run_next = {**run, "cursor": state["cursor"]}

    # Elements the producer wrote that cannot be read back. Reported rather
    # than skipped — a silently shorter list reads as a model that traced
    # less, which is how the same bug hid on /ai-agent.
    lost_note = f" · {state['lost']} lost from the buffer" if state.get("lost") else ""

    if not state["done"]:
        n = len(elements)
        return (
            cmd,
            f"Tracing… {n} element{'s' if n != 1 else ''} so far "
            f"({state['elapsed']:.0f}s){lost_note}",
            "orange" if state.get("lost") else "gray",
            run_next,
            False,
        )

    scene_stream.forget(run["id"])
    if not elements:
        return (
            no_update,
            "The model returned no elements. Try a clearer image, a higher "
            "budget, or a different model.",
            "yellow",
            None,
            True,
        )

    meta = state["meta"] or {}
    price = MODEL_PRICING.get(run.get("model"), (0, 0))
    cost = (
        meta.get("input_tokens", 0) * price[0]
        + meta.get("output_tokens", 0) * price[1]
    ) / 1_000_000
    status = (
        f"{MODEL_LABEL.get(run.get('model'), run.get('model'))} · "
        f"{len(elements)} elements in {state['elapsed']:.0f}s · "
        f"{meta.get('output_tokens', 0):,} out / "
        f"{meta.get('input_tokens', 0):,} in · ~${cost:.3f}"
    )
    return (
        {
            "id": f"trace-final-{run['id'][:8]}",
            "type": "updateScene",
            "payload": {"elements": elements, "captureUpdate": "IMMEDIATELY"},
        },
        status,
        "green",
        None,
        True,
    )


@callback(
    Output("trace-status", "children", allow_duplicate=True),
    Output("trace-status", "color", allow_duplicate=True),
    Output("trace-run", "data", allow_duplicate=True),
    Output("trace-tick", "disabled", allow_duplicate=True),
    Input("trace-stop", "n_clicks"),
    State("trace-run", "data"),
    prevent_initial_call=True,
)
def _stop(_clicks, run):
    """Press the brakes: stop the trace, keep what it has drawn.

    Disabling the ticker would only stop the PAGE watching; the worker would
    keep pulling tokens to the full budget with nobody reading them.
    `scene_stream.cancel` closes the provider stream, so billing stops at the
    tokens already produced. See lib/scene_stream.cancel.
    """
    if not run or not run.get("id"):
        return no_update, no_update, no_update, True

    scene_stream.cancel(run["id"])
    drawn = len(scene_stream.take(run["id"], 0)["all"])
    return (
        f"Stopped. {drawn} element{'s' if drawn != 1 else ''} kept; no further "
        f"tokens are being generated.",
        "yellow",
        None,
        True,
    )


@callback(
    Output("trace-run-btn", "loading"),
    Output("trace-run-btn", "disabled"),
    Output("trace-stop", "disabled"),
    Output("trace-upload", "disabled"),
    Output("trace-model", "disabled"),
    Output("trace-max-tokens", "disabled"),
    Input("trace-tick", "disabled"),
)
def _lock_controls(tick_disabled):
    """The ticker being enabled IS "a trace is in progress"."""
    drawing = not tick_disabled
    # `or not ANY_KEY` keeps the run button off for good on a keyless site.
    off = drawing or not ANY_KEY
    # Stop is enabled precisely when a trace is running.
    return drawing, off, not drawing, off, off, off
