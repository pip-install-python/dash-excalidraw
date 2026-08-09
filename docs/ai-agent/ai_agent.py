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
from docs._shared import canvas_frame, sync_canvas_theme

sync_canvas_theme("ai-canvas")

# ---------------------------------------------------------------------------
# Prompt template (domain-specific instructions for producing Excalidraw JSON)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert at producing Excalidraw scenes as JSON.

Given a user request for a diagram, return ONLY a JSON object that can be used
directly as Excalidraw `initialData`. No prose, no markdown fences, no
explanation — JSON only.

REQUIRED TOP-LEVEL SHAPE
{
  "type": "excalidraw",
  "version": 2,
  "source": "ai-agent",
  "elements": [...],
  "appState": {"viewBackgroundColor": "#ffffff", "gridSize": null},
  "files": {}
}

ELEMENT TYPES
- rectangle, ellipse, diamond — nodes / shapes
- text                         — titles, headers, labels, annotations
- arrow, line                  — connections (arrow for directional)
- freedraw                     — hand-drawn strokes (use sparingly)

REQUIRED PER-ELEMENT FIELDS
Every element needs: id (unique string), type, x, y, width, height,
angle (0), strokeColor, backgroundColor, fillStyle ("solid" is safest),
strokeWidth, strokeStyle ("solid"), roughness (0 clean / 1 hand-drawn),
opacity (100), seed (positive int), version (1), versionNonce (positive int),
isDeleted (false), groupIds ([]), frameId (null), boundElements ([]),
updated (1), link (null), locked (false), roundness:
  - null                    for text, arrows, lines
  - {"type": 2}             for ellipses
  - {"type": 3}             for rectangles, diamonds, rounded rects

TYPOGRAPHY HIERARCHY — apply every time you emit text

Every diagram benefits from a clear visual hierarchy. Use the ranges below;
DO NOT make everything the same size.

  TITLE           fontSize 28–36, fontFamily 2, textAlign "center",
                  fontFamily 2 (sans-serif), strokeColor "#1e1e1e" or a
                  strong brand color. One title per diagram, at the top.

  SECTION HEADER  fontSize 18–22, fontFamily 2, bold-feeling (leave weight
                  default; size carries the emphasis). One per logical group.

  BODY / LABEL    fontSize 14–16, fontFamily 2. Labels inside shapes, short
                  descriptions, edge labels.

  CAPTION / META  fontSize 11–13, fontFamily 2, strokeColor "#6b7280". Small
                  annotations, units, timestamps.

  CODE / KEYWORD  fontSize 13–14, fontFamily 3 (Cascadia / monospace). Only
                  for function names, identifiers, literal code.

Use fontFamily 1 (Virgil, hand-drawn) ONLY when the user asks for a
"hand-drawn" / "sketch" feel.

TEXT DIMENSIONS — CRITICAL

Text width/height must accommodate the actual text or Excalidraw clips it
visually until the user resizes. Use these formulas:

  width  ≈ max(len(longest_line) * fontSize * 0.6,  fontSize * 3)
  height = fontSize * 1.25 * number_of_lines
  lineHeight = 1.25  (always)

Extra fields on every text element:
  text              the visible string (include \\n for line breaks)
  fontSize          from the hierarchy above
  fontFamily        1, 2, or 3
  textAlign         "center" for titles / shape-bound labels, "left" for
                    annotations and multi-line prose
  verticalAlign     "middle" when containerId is set, "top" otherwise
  containerId       the shape's id when bound to a shape, null otherwise
  originalText      same string as `text`
  lineHeight        1.25

TEXT INSIDE A SHAPE
  1. Create the shape (rectangle / ellipse / diamond).
  2. Create a text element with containerId = <shape_id>, verticalAlign:
     "middle", textAlign: "center".
  3. Add {"id": <text_id>, "type": "text"} to the shape's boundElements.
  4. Position the text at (shape.x + padding, shape.y + padding).

ARROW / LINE fields
  points             [[0, 0], [dx, dy]]
  startBinding       {"elementId": "<shape_id>", "focus": 0, "gap": 1} or null
  endBinding         same shape or null
  lastCommittedPoint null
  startArrowhead     null or "arrow"
  endArrowhead       null or "arrow"  (arrow endpoint usually "arrow")
  elbowed            false            (use true for flowchart right-angle runs)

LAYOUT
- Canvas: assume 1200x800. Keep content inside this box when possible.
- Reserve ~80 px at the top for the title when one is present.
- Spacing between logical groups: 40–80 px.
- Shape padding for bound text: 12–20 px.
- Align shape centers on a 20-px grid for visual cleanliness.

COLOR PALETTE — pick one accent per logical group

Use these pairs (bg, stroke, text) so text stays legible on tinted fills:

  Indigo   bg "#dbe4ff"  stroke "#4263eb"  text "#1e3a8a"
  Teal     bg "#c3fae8"  stroke "#0ca678"  text "#0b7285"
  Orange   bg "#ffe8cc"  stroke "#e67700"  text "#d9480f"
  Rose     bg "#ffe0ec"  stroke "#e64980"  text "#a61e4d"
  Grape    bg "#eebefa"  stroke "#ae3ec9"  text "#862e9c"
  Gray     bg "#f1f3f5"  stroke "#495057"  text "#212529"

Default strokeColor when no tint applies: "#1e1e1e".
Default text on plain white background: "#1e1e1e".
Titles may use a color drawn from the dominant group to create rhythm.

STYLE DISCIPLINE
- fillStyle "solid" unless the user asks for hatching / hand-drawn.
- roughness 0 for clean professional diagrams, 1 for hand-drawn feel.
- strokeWidth 1 for most shapes; 2 for titles / emphasis containers.
- strokeStyle "solid" unless a dashed relationship needs "dashed".

Return ONLY the JSON object — no preamble, no markdown fence, no epilogue."""

# Claude model options (exact IDs — no date suffixes; these strings are
# complete as written).
CLAUDE_MODELS = [
    {"value": "claude-opus-5", "label": "Claude Opus 5"},
    {"value": "claude-opus-4-7", "label": "Claude Opus 4.7"},
    {"value": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6"},
    {"value": "claude-haiku-4-5", "label": "Claude Haiku 4.5"},
]

# Per-model output ceiling. Well below each model's absolute max (Opus 5 and
# Opus 4.7 support 128K output), but large enough that a detailed Excalidraw
# scene never truncates mid-element. All calls stream, so the SDK's
# non-streaming HTTP deadline doesn't bite at any of these values.
#
# ONE THING TO KNOW ABOUT OPUS 5: thinking is ON BY DEFAULT there — omitting
# the `thinking` parameter runs adaptive thinking, where on Opus 4.7 the same
# omission meant no thinking at all. `max_tokens` caps thinking AND response
# text together, so a budget sized tightly around the answer on 4.7 can
# truncate on 5. 64K is generous for a scene JSON either way; if you lower
# these numbers, lower them for 4.7 first.
CLAUDE_MAX_TOKENS = {
    # MEASURED, not guessed. On Opus 5 this number is a latency control, not
    # just a safety net, because `max_tokens` bounds thinking AND text
    # together and adaptive thinking will happily use the whole budget:
    #
    #   "microservices architecture diagram" @ 64000, default effort
    #       -> 473s wall, 43,702 output tokens (~$1.09 of output at $25/1M)
    #   same prompt      @ 24000, effort=low
    #       -> ~99s wall, 12,276 output tokens (~$0.31)
    #
    # Nearly eight minutes reads as a hung page, and the spinner gives no way
    # to tell "thinking hard" from "broken". Bounding the budget bounds the
    # worst case; `stop_reason: max_tokens` is surfaced explicitly below, so
    # a scene that genuinely needs more says so instead of truncating quietly.
    "claude-opus-5": 24000,
    "claude-opus-4-7": 64000,
    "claude-sonnet-4-6": 64000,
    "claude-haiku-4-5": 64000,
}

# Effort is the other half of the latency control, and the bigger lever on
# Opus 5 — `low` and `medium` are unusually strong there. Generating a scene
# is structured output, not deep reasoning, so `low` is the right default:
# measured 38s vs 55s at the `high` default on a simple prompt, with no
# quality difference in the resulting scene.
#
# None means "don't send output_config at all" — Haiku 4.5 rejects the effort
# parameter outright, so this must stay a per-model opt-in rather than a
# blanket default.
CLAUDE_EFFORT = {
    "claude-opus-5": "low",
    "claude-opus-4-7": "low",
    "claude-sonnet-4-6": None,
    "claude-haiku-4-5": None,
}

GEMINI_MODELS = [
    {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
    {"value": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
]

GEMINI_MAX_TOKENS = 64000

HAS_CLAUDE_KEY = bool(os.environ.get("ANTHROPIC_API_KEY"))
HAS_GEMINI_KEY = bool(os.environ.get("GEMINI_API_KEY")) or bool(
    os.environ.get("GOOGLE_API_KEY")
)


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def _extract_json_block(text: str) -> str:
    """Pull a single JSON object out of arbitrary AI output.

    The previous regex-based approach used `\\{[\\s\\S]*?\\}` which is
    non-greedy and therefore stopped at the first `}` it found — for an
    Excalidraw scene that hits the first `}` on a nested element and
    truncates the rest of the JSON, producing a parse error deep in the
    response. Instead, scan character-by-character with a brace counter
    that is aware of string literals and escape sequences.
    """
    text = text.strip()

    # Strip markdown code fences if present (```json ... ``` or ``` ... ```).
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl > 0:
            text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    start = text.find("{")
    if start < 0:
        return text

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if in_string:
            if ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    # Unterminated — return what we have and let json.loads surface the
    # exact location where the model ran out of tokens.
    return text[start:]


def _cleanup_json(text: str) -> str:
    """Best-effort fixups for JSON-ish strings common models emit.

    - Removes trailing commas before `}` / `]` (valid JS, invalid JSON).
    Strings are not scanned for matches because the trailing-comma pattern
    is highly specific and false positives are rare in practice.
    """
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _spend_allowed() -> bool:
    """May the current request spend API credits?

    Deliberately fails CLOSED in production and OPEN in local development,
    which is the inverse of how the page-tier machinery degrades:

    * Clerk configured  -> only a signed-in viewer may generate.
    * Clerk absent, running on a hosting platform (RENDER / APP_ENV) -> nobody
      may generate. A deployment that forgot its CLERK_* vars must not hand
      the whole internet a metered endpoint.
    * Clerk absent, local dev -> allowed, so the demo is usable offline.

    Read at CALL time, never at import — the same rule lib/auth.py documents,
    and the reason a module-level constant would be wrong here.
    """
    import os

    from lib import auth

    if auth.clerk_enabled():
        return auth.current_user() is not None

    in_production = bool(
        os.environ.get("RENDER") or os.environ.get("APP_ENV") == "production"
    )
    return not in_production


def _call_claude(model: str, user_prompt: str) -> str:
    """Streaming Claude call with prompt caching on the system block.

    We stream — even though we wait for the full response — because the
    non-streaming endpoint has a synchronous HTTP deadline the SDK treats
    as a hard timeout. At `max_tokens` in the 30K–128K range on Opus /
    Sonnet that deadline routinely trips; streaming lifts that constraint
    and lets the model run to its natural end.
    """
    import anthropic

    client = anthropic.Anthropic()
    max_tokens = CLAUDE_MAX_TOKENS.get(model, 32000)

    kwargs = {}
    effort = CLAUDE_EFFORT.get(model)
    if effort:
        # Only sent for models that accept it — see CLAUDE_EFFORT.
        kwargs["output_config"] = {"effort": effort}

    with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
        **kwargs,
    ) as stream:
        final = stream.get_final_message()

    stop_reason = getattr(final, "stop_reason", None)

    # CHECK stop_reason BEFORE READING content. Opus 5 ships elevated safety
    # classifiers that can decline a request: the call returns a normal HTTP
    # 200 with `stop_reason: "refusal"` and an empty (or partial) content
    # list, not an exception. Reading content first would hand
    # _parse_and_normalize an empty string and surface as an inscrutable JSON
    # error several frames away from the actual cause.
    #
    # A drawing prompt is an unlikely trigger, but "unlikely" is exactly the
    # failure that gets diagnosed as a parser bug.
    if stop_reason == "refusal":
        details = getattr(final, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise ValueError(
            "Claude's safety classifiers declined this request"
            + (f" (category: {category})" if category else "")
            + ". Nothing was generated. Rephrase the prompt, or pick a "
            "different model from the selector."
        )

    text = next(
        (b.text for b in final.content if getattr(b, "type", None) == "text"), ""
    )
    # Surface truncation explicitly — better to tell the user than to let
    # _parse_and_normalize fail deep inside malformed JSON.
    if stop_reason == "max_tokens":
        raise ValueError(
            f"Claude hit max_tokens={max_tokens} and was cut off mid-response. "
            f"Raise `CLAUDE_MAX_TOKENS[{model!r}]` or ask for a smaller scene."
        )
    return text


def _call_gemini(model: str, user_prompt: str) -> str:
    """Gemini call with a generous output budget and JSON mime-type hint."""
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed. `pip install google-genai`."
        ) from exc

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    client = genai.Client(api_key=key)
    full_prompt = SYSTEM_PROMPT + "\n\nUser request: " + user_prompt

    # `response_mime_type="application/json"` pushes the model toward a
    # pure-JSON response with no prose wrapper — removes a whole class of
    # "extract JSON from markdown fence" parsing failures.
    config = genai_types.GenerateContentConfig(
        max_output_tokens=GEMINI_MAX_TOKENS,
        response_mime_type="application/json",
    )
    resp = client.models.generate_content(
        model=model, contents=full_prompt, config=config
    )
    # Surface truncation. Gemini exposes it via `finish_reason` on candidates.
    try:
        fin = resp.candidates[0].finish_reason
        if str(fin).upper().endswith("MAX_TOKENS"):
            raise ValueError(
                f"Gemini hit max_output_tokens={GEMINI_MAX_TOKENS} and was cut off "
                f"mid-response. Raise `GEMINI_MAX_TOKENS` or ask for a smaller scene."
            )
    except (AttributeError, IndexError, TypeError):
        pass
    return resp.text or ""


def _coerce_types(obj: Any) -> Any:
    """Mirror of the reference app's post-processor: coerce numeric fields and
    drop stringified literals ("null"/"true"/"false"). Tolerant of AI output
    that sometimes quotes numbers."""
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            v2 = _coerce_types(v)
            if k in ("seed", "version", "versionNonce", "updated") and isinstance(
                v2, (str, float)
            ):
                try:
                    v2 = int(float(v2))
                except (TypeError, ValueError):
                    pass
            elif k in (
                "x",
                "y",
                "width",
                "height",
                "angle",
                "strokeWidth",
                "opacity",
                "fontSize",
                "roughness",
            ) and isinstance(v2, str):
                try:
                    v2 = float(v2)
                except (TypeError, ValueError):
                    pass
            out[k] = v2
        # fill in sensible defaults so Excalidraw doesn't reject the element
        if out.get("type") and "id" in out:
            out.setdefault("isDeleted", False)
            out.setdefault("updated", 1)
            out.setdefault("version", 1)
            out.setdefault("versionNonce", int(uuid.uuid4().int % (10**9)))
            out.setdefault("seed", int(uuid.uuid4().int % (10**9)))
            out.setdefault("groupIds", [])
            out.setdefault("frameId", None)
            out.setdefault("boundElements", [])
            out.setdefault("link", None)
            out.setdefault("locked", False)
            out.setdefault("opacity", 100)
            if out.get("type") == "text" and "roundness" not in out:
                out["roundness"] = None
        return out
    if isinstance(obj, list):
        return [_coerce_types(x) for x in obj]
    if obj in ("null", "None"):
        return None
    if obj == "true":
        return True
    if obj == "false":
        return False
    return obj


def _parse_and_normalize(raw: str) -> Dict[str, Any]:
    extracted = _extract_json_block(raw)
    cleaned = _cleanup_json(extracted)
    parsed = json.loads(cleaned)
    parsed = _coerce_types(parsed)
    if not isinstance(parsed, dict):
        raise ValueError("AI response was not a JSON object.")
    parsed.setdefault("type", "excalidraw")
    parsed.setdefault("version", 2)
    parsed.setdefault("source", "ai-agent")
    parsed.setdefault("elements", [])
    parsed.setdefault("appState", {"viewBackgroundColor": "#ffffff", "gridSize": None})
    parsed.setdefault("files", {})
    return parsed


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
                                dmc.NumberInput(
                                    id="ai-seed",
                                    label="Element-id seed",
                                    description="Used for stable replay; bump to get a fresh scene id namespace",
                                    value=1,
                                    min=1,
                                ),
                                span={"base": 12, "sm": 5},
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
def _generate(_gen_clicks, provider, model, prompt):
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
            raw = _call_claude(model, prompt.strip())
        else:
            raw = _call_gemini(model, prompt.strip())
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
    status = (
        f"Generated via {provider} / {model} — {element_count} element"
        f"{'s' if element_count != 1 else ''} in {elapsed:.0f}s."
    )
    return cmd, status, "green", pretty_raw, pretty_parsed, raw