"""Scene generation shared by the AI pages.

Lives in lib/ rather than in a page module because TWO pages need it —
/ai-agent (one scene) and /benchmark (a matrix of them). A docs page that
imported another docs page would re-execute its module and register every one
of its callbacks a second time, which Dash rejects. Shared logic therefore has
to sit outside docs/.

Nothing here is part of the published dash-excalidraw package; it belongs to
the documentation site.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict

from lib import spend

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
# ORDER MATTERS: both pages use CLAUDE_MODELS[0] as the default selection, so
# whatever sits first is what an unattended visitor spends money on. Claude
# Fable 5.1 is the most capable of these and is listed second on purpose — at
# $10/$50 per 1M it is twice Opus 5's rate, and making the most expensive
# model the default is the owner's decision, not a side effect of adding it.
# Every environment variable that can put a PAID API within reach of this
# module. Two things read this tuple, and that is the whole point:
#
#   * tests/conftest.py blanks every name in it before anything imports the
#     app, so the suite cannot make a real call off a developer's .env;
#   * tests/test_provider_keys.py asserts this tuple equals the set of key
#     names actually read below.
#
# A hand-kept list in conftest is what let this hole exist: CHATGPT_API_KEY
# was added to the app and not to the list, so on any machine holding that
# key the suite would have called the live endpoint. Deriving the list from
# the module means the next provider cannot reopen it by being forgotten.
PROVIDER_KEY_VARS = (
    "ANTHROPIC_API_KEY",
    # The SDK reads this one too, without this module ever naming it — so
    # blanking only ANTHROPIC_API_KEY would still leave a configured client.
    "ANTHROPIC_AUTH_TOKEN",
    "CHATGPT_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)

CLAUDE_MODELS = [
    {"value": "claude-opus-5", "label": "Claude Opus 5"},
    {"value": "claude-fable-5-1", "label": "Claude Fable 5.1"},
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
    # Claude Fable 5.1 gets Opus 5's tighter budget for the same reason, and
    # the reason is stronger here: thinking is ALWAYS on (it cannot be
    # disabled — `{"type": "disabled"}` and `budget_tokens` both 400), and
    # its turns on hard prompts run longer than any model above. Same
    # arithmetic as the Opus 5 note: max_tokens bounds thinking AND text, so
    # this is a latency ceiling first and a safety net second. At $50/1M
    # output it is also the budget that bounds the worst-case bill.
    "claude-fable-5-1": 24000,
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
# Selectable in the UI. "none" means send no output_config at all, which is
# the only valid choice for models that reject the parameter (Haiku 4.5) and
# a useful benchmark baseline elsewhere — it exercises each model's own
# default rather than a level you picked.
EFFORT_LEVELS = [
    {"value": "none", "label": "none (model default)"},
    {"value": "low", "label": "low"},
    {"value": "medium", "label": "medium"},
    {"value": "high", "label": "high"},
    {"value": "xhigh", "label": "xhigh"},
    {"value": "max", "label": "max"},
]

# Models that accept output_config.effort at all. Haiku 4.5 rejects it, so
# sending a level there is a 400 rather than a slower answer — the control has
# to be gated per model, not merely defaulted.
EFFORT_CAPABLE = {
    "claude-opus-5",
    "claude-fable-5-1",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
}

# Effort levels a model rejects even though it accepts the parameter at all.
# MEASURED from `GET /v1/models/{id}` on this deployment's key (2026-09-10):
# claude-sonnet-4-6 reports `effort.xhigh.supported: false` while every other
# level is true. It is the only model in CLAUDE_MODELS with a hole in the
# middle of its range — Haiku 4.5 rejects the parameter outright and is
# already handled by EFFORT_CAPABLE.
#
# Sending it is a 400, and this app was offering `xhigh` in the selector for
# that model. The level is therefore DROPPED rather than sent, which is the
# same treatment Haiku's effort already gets: the request runs at the model's
# own default and the meta reports `effort_ignored`.
EFFORT_UNSUPPORTED = {
    "claude-sonnet-4-6": {"xhigh"},
}


def supported_efforts(model: str) -> list[str]:
    """The effort levels this model will actually accept, for a UI to offer.

    A selector that lists a level the API rejects is a 400 waiting for
    whoever picks it, and the failure arrives as a provider error rather than
    as anything the page could explain.
    """
    if model not in EFFORT_CAPABLE:
        return ["none"]
    blocked = EFFORT_UNSUPPORTED.get(model, set())
    return [e["value"] for e in EFFORT_LEVELS if e["value"] not in blocked]


# USD per 1M tokens (input, output), for the cost estimate in the status line.
# A LOCAL ESTIMATE, not a bill: it ignores cache-write premiums and every
# discount, and published prices change. It is here so a benchmark sweep can
# be compared on cost as well as latency, which is the whole point of being
# able to vary effort and budget.
CLAUDE_PRICING = {
    "claude-opus-5": (5.0, 25.0),
    # The most expensive row here by a factor of two on both sides. Worth
    # knowing before a /benchmark sweep: six variants that each run their
    # whole 24K budget is $7.20 of output on Fable 5.1 against $3.60 on
    # Opus 5, which is exactly what the page's cost estimate exists to show
    # you BEFORE you press the button.
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

CLAUDE_EFFORT = {
    "claude-opus-5": "low",
    # Same default as Opus 5 and for the same reason — a scene is structured
    # output, not deep reasoning, and low effort on this model is stronger
    # than high effort on older ones. On /benchmark you can sweep it up to
    # `max`; this is only where the selector starts.
    "claude-fable-5-1": "low",
    "claude-opus-4-7": "low",
    "claude-sonnet-4-6": None,
    "claude-haiku-4-5": None,
}

OPENAI_MODELS = [
    {"value": "gpt-6-astra", "label": "GPT-6 Astra"},
    {"value": "gpt-5.6-sol", "label": "GPT-5.6 Sol"},
    {"value": "gpt-5.6-terra", "label": "GPT-5.6 Terra"},
    {"value": "gpt-5.6-luna", "label": "GPT-5.6 Luna"},
]

# USD per 1M tokens (input, output). Cached input is cheaper still (a tenth on
# all four) and >272K-token prompts carry a 2x input / 1.5x output multiplier
# on terra and luna — neither applies at the prompt sizes this page sends, so
# neither is modelled here.
OPENAI_PRICING = {
    "gpt-6-astra": (10.0, 50.0),
    "gpt-5.6-sol": (4.0, 20.0),
    "gpt-5.6-terra": (2.0, 12.0),
    "gpt-5.6-luna": (0.2, 1.2),
}

# All four cap at 128K output. The ladder below is deliberately inverse to
# price, so a default run lands in the same rough band whichever you pick:
#   astra  24K x $50  = $1.20      terra  32K x $12  = $0.38
#   sol    24K x $20  = $0.48      luna   64K x $1.2 = $0.08
# Same reasoning as the Claude table: these are reasoning models, the budget
# covers reasoning AND output, and the number is a latency-and-bill ceiling
# rather than a target.
OPENAI_MAX_TOKENS = {
    "gpt-6-astra": 24000,
    "gpt-5.6-sol": 24000,
    "gpt-5.6-terra": 32000,
    "gpt-5.6-luna": 64000,
}

# `low` for the same reason as Claude: a scene is structured output, not deep
# reasoning. OpenAI's own default is `medium`.
OPENAI_EFFORT = {
    "gpt-6-astra": "low",
    "gpt-5.6-sol": "low",
    "gpt-5.6-terra": "low",
    "gpt-5.6-luna": "low",
}

# The API's `ReasoningEffort` literal accepts none/minimal/low/medium/high/
# xhigh/max, so every level this UI offers is valid — except that astra's model
# page does not list `none`. The app sends NO reasoning parameter for "none"
# anyway (the same meaning it has for Claude), so that difference never
# reaches the wire.
EFFORT_CAPABLE = EFFORT_CAPABLE | {m["value"] for m in OPENAI_MODELS}

GEMINI_MODELS = [
    {"value": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
    {"value": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
]

GEMINI_MAX_TOKENS = 64000

# USD per 1M tokens (input, output). Added so Gemini COUNTS towards the daily
# ceiling rather than merely being refused by it — without a price its calls
# could not be recorded, so a Gemini-only day could pass the cap without ever
# tripping it. These are the standard (<=200K-prompt) rates; both models
# charge more above that threshold, which nothing this app sends approaches.
#
# Gemini still does not join COMPARABLE_MODELS: /benchmark needs a budget and
# an effort control to make a comparison honest, and `_call_gemini` has
# neither. Being priceable and being comparable are different questions.
GEMINI_PRICING = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
}


# ---------------------------------------------------------------------------
#  One registry across providers
# ---------------------------------------------------------------------------
#
# /benchmark can put a Claude model and a ChatGPT model side by side on the
# same prompt, which only works if pricing, budgets, defaults and dispatch are
# reachable by MODEL ID alone — the provider is then a property of the model
# rather than a separate control the two lists have to be kept in step with.
PROVIDER_OF = {
    **{m["value"]: "claude" for m in CLAUDE_MODELS},
    **{m["value"]: "chatgpt" for m in OPENAI_MODELS},
    **{m["value"]: "gemini" for m in GEMINI_MODELS},
}
MODEL_LABEL = {
    m["value"]: m["label"] for m in CLAUDE_MODELS + OPENAI_MODELS + GEMINI_MODELS
}
MODEL_PRICING = {**CLAUDE_PRICING, **OPENAI_PRICING, **GEMINI_PRICING}
MODEL_MAX_TOKENS = {**CLAUDE_MAX_TOKENS, **OPENAI_MAX_TOKENS}
MODEL_EFFORT = {**CLAUDE_EFFORT, **OPENAI_EFFORT}

# Models that can take part in a cross-provider comparison: they accept a
# budget and an effort, and they have a published price. Gemini is out — it is
# called through a different signature with neither control and no entry in
# MODEL_PRICING, so a "compare" cell for it could show a drawing but never an
# honest cost or a matched setting.
COMPARABLE_MODELS = [
    {"value": m["value"], "label": m["label"]} for m in CLAUDE_MODELS + OPENAI_MODELS
]

# Models that accept an image alongside the prompt — what /trace-image needs.
# MEASURED 2026-09-10, not assumed: every Claude entry reports
# `image_input.supported: true` from `GET /v1/models/{id}`, and all four
# OpenAI entries list input modalities "text, image" on their model pages. All
# nine qualify today; the set exists so that stops being an assumption the
# moment a text-only model is added to either list.
VISION_MODELS = {m["value"] for m in COMPARABLE_MODELS}


class ElementStreamParser:
    """Pulls whole elements out of a scene JSON that is still being written.

    The model emits one big object; the canvas wants to show shapes as they
    arrive. So rather than waiting for the closing brace and rendering 40
    elements at once, this scans the `"elements"` array and hands back each
    object the moment ITS braces balance.

    Why hand-rolled rather than an incremental JSON library: the useful unit
    here is "one complete element", not "one complete token" — and the parse
    has to tolerate a document that will not be valid JSON until the very last
    chunk. `json.loads` on each candidate element is still doing the real
    parsing; this only finds the boundaries.

    The two things that make brace-counting wrong if you skip them are strings
    containing braces (`"text": "if (x) {y}"`) and escaped quotes inside them.
    Both are handled below, and both are in the tests.
    """

    def __init__(self) -> None:
        self._buf = ""
        self._in_elements = False
        self._depth = 0
        self._start = -1
        self._in_string = False
        self._escaped = False
        self._done = False
        # Where the scan reached last time. This has to persist: the string
        # and depth state carries across feeds, so restarting at 0 each call
        # would re-count every brace already seen — which silently produces
        # zero elements when the chunks are small (one character per feed
        # being the worst case, and exactly how a token stream arrives).
        self._pos = 0

    def feed(self, chunk: str) -> list[dict]:
        """Add text; return every element that became complete because of it."""
        if self._done or not chunk:
            return []
        self._buf += chunk
        out: list[dict] = []

        if not self._in_elements:
            # Find the array opening. Anything before it (the envelope's other
            # keys) is not our business.
            marker = self._buf.find('"elements"')
            if marker == -1:
                return []
            bracket = self._buf.find("[", marker)
            if bracket == -1:
                return []
            self._in_elements = True
            self._buf = self._buf[bracket + 1 :]
            self._pos = 0

        i = self._pos
        while i < len(self._buf):
            ch = self._buf[i]

            if self._in_string:
                if self._escaped:
                    self._escaped = False
                elif ch == "\\":
                    self._escaped = True
                elif ch == '"':
                    self._in_string = False
                i += 1
                continue

            if ch == '"':
                self._in_string = True
            elif ch == "{":
                if self._depth == 0:
                    self._start = i
                self._depth += 1
            elif ch == "}":
                self._depth -= 1
                if self._depth == 0 and self._start >= 0:
                    candidate = self._buf[self._start : i + 1]
                    try:
                        element = json.loads(candidate)
                    except ValueError:
                        # Not an element after all; drop it rather than stall
                        # the stream on one malformed object.
                        element = None
                    if isinstance(element, dict):
                        out.append(element)
                    # Consume what we just emitted and restart the scan.
                    self._buf = self._buf[i + 1 :]
                    self._start = -1
                    i = 0
                    self._pos = 0
                    continue
            elif ch == "]" and self._depth == 0:
                # End of the elements array — everything after is the
                # envelope's tail and no more elements are coming.
                self._done = True
                self._pos = i
                break

            i += 1

        else:
            # Loop ran to the end without breaking: remember where to resume.
            self._pos = i

        return out

    @property
    def finished(self) -> bool:
        return self._done


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


TRACE_SYSTEM_PROMPT = (
    SYSTEM_PROMPT.split("ELEMENT TYPES")[0]
    + """ELEMENT TYPES
- rectangle, ellipse, diamond — shapes and regions
- text                         — any legible words in the image
- arrow, line                  — connectors, rules, edges
- freedraw                     — irregular contours, sparingly

YOU ARE TRACING A REFERENCE IMAGE.
Reproduce it as closely as these six primitives allow. You are not describing
the image and not improving it — someone should be able to put your drawing
beside it and see the same arrangement.

WHAT TO MATCH, IN ORDER
1. LAYOUT. Relative position and size come first. A box in the upper-left
   belongs in the upper-left, at roughly the same proportion of the canvas.
2. STRUCTURE. Count of distinct shapes, and how they connect or nest.
3. TEXT. Transcribe words you can actually read, positioned where they sit.
   Do not invent labels for text you cannot make out.
4. COLOUR. Approximate strokeColor and backgroundColor from the image rather
   than defaulting to black on white.

WHAT NOT TO DO
- Do not approximate photographic detail, gradients, shadows or texture with
  hundreds of freedraw strokes. Six clean shapes that capture the arrangement
  beat six hundred that capture noise and exhaust the token budget.
- Do not add a title, caption, legend or annotation that is not in the image.
- Do not stylise. If the image is a plain flowchart, draw a plain flowchart.

Work in a canvas roughly 1200x800 unless the image is clearly portrait, and
keep the aspect ratio of the original arrangement.
"""
    + SYSTEM_PROMPT.split("ELEMENT TYPES", 1)[1].split("STYLE DISCIPLINE")[0]
    + """STYLE DISCIPLINE
- roughness 0 unless the reference is itself hand-drawn.
- fillStyle "solid" when a region reads as filled in the image.

Return ONLY the JSON object — no preamble, no markdown fence, no epilogue.
"""
)


# The token-budget control's range. Defined here rather than inline in each
# NumberInput so the clamp below and the widgets cannot drift apart.
BUDGET_MIN = 1000
BUDGET_MAX = 128000

# A number typed into a dmc.NumberInput does not arrive as an int. Mid-edit it
# arrives as whatever is in the box — "64.000" was the value that crashed both
# pages, and `int("64.000")` raises rather than returning anything.
#
# `64.000` also shows why "just call float()" is the wrong reflex: read as a
# decimal it is 64 tokens, read as grouped digits it is 64,000 — a
# thousand-fold difference in what the user is quoted and then billed. The
# grouping reading is the right one here (the control's own range starts at
# 1,000 and steps in 4,000s, so 64 was never on offer), but only when the
# separator is followed by exactly three digits. Anything else falls through
# to a plain float parse.
_GROUPED = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")


def coerce_budget(value, default: int | None = None) -> int | None:
    """A token budget from the UI, or `default` when it cannot be read.

    Never raises. This sits in front of BOTH the cost estimate and the paid
    call, because a value that cannot be parsed is a 500 on whichever it
    reaches first — and the one it reaches first is usually the estimate,
    which is the harmless one.
    """
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(" ", "")
        if not text:
            return default
        if _GROUPED.match(text):
            text = text.replace(".", "").replace(",", "")
        else:
            text = text.replace(",", "")
        try:
            number = float(text)
        except ValueError:
            return default
    if number != number or number in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return max(BUDGET_MIN, min(BUDGET_MAX, int(number)))


# ---------------------------------------------------------------------------
#  Cost estimation — what both pages show BEFORE you press the button.
# ---------------------------------------------------------------------------
#
# The honest shape of this problem: `max_tokens` is a CEILING, not a spend.
# What you actually pay is whatever the model generates under it, and on a
# thinking model that number moves with effort. So a single figure is either
# pessimistic enough to be useless or optimistic enough to mislead — both
# pages therefore show a typical figure AND the ceiling.
#
# HOW MUCH OF THE BUDGET AN EFFORT LEVEL ACTUALLY USES. Two real measurements
# exist, both Opus 5 on the "microservices architecture diagram" prompt (the
# same run recorded against CLAUDE_MAX_TOKENS above):
#
#     effort=low          12,276 of 24,000  -> 0.51
#     default (= high)    43,702 of 64,000  -> 0.68
#
# `low` and `high` below are those two numbers. **medium, xhigh and max are
# interpolated and extrapolated from them, not measured**, and all four come
# from ONE prompt on ONE model — a denser scene or a different model will land
# somewhere else. That is exactly why the ceiling is always shown next to the
# estimate: the fraction is a guide, the ceiling is the bound.
EFFORT_UTILISATION = {
    "none": 0.70,  # no output_config sent -> the model's own default (high)
    "low": 0.51,   # MEASURED
    "medium": 0.60,
    "high": 0.68,  # MEASURED
    "xhigh": 0.85,
    "max": 0.95,
}

# Input is priced too, but it is not where the money goes. The system prompt
# is ~1,300 tokens; against a 24K output budget that is 1.1% of the bill on
# every model in CLAUDE_PRICING, and prompt caching drops the repeat cost to a
# tenth of that. It is included below at the UNCACHED rate so the ceiling is a
# genuine upper bound rather than one with a term quietly missing.
#
# The token count is a chars/4 approximation rather than a `count_tokens` call:
# this runs on every keystroke of the controls, and a network round-trip per
# edit would be a poor trade for a term worth ~1% — an approximation error here
# is a rounding error on a rounding error.
_APPROX_INPUT_TOKENS = len(SYSTEM_PROMPT) // 4 + 200  # + headroom for the user prompt


def resolve_effort(model: str, effort: str | None) -> str | None:
    """The effort that will ACTUALLY be sent, or None for "send nothing".

    Shared by the estimator and `_call_claude` on purpose. A label that
    reported a level the request then dropped would be a lie in the one place
    the user is deciding whether to spend money — and "Haiku ignores effort"
    is exactly the case where a naive estimate would over-quote.
    """
    if effort is None:
        effort = CLAUDE_EFFORT.get(model) or "none"
    if effort == "none" or model not in EFFORT_CAPABLE:
        return None
    # MOVED here from `_call_claude` (b94ff6e lines 436-441): the same rule, in
    # the one place that now decides what actually gets sent. A level the model
    # rejects is dropped rather than sent. Sonnet 4.6 takes
    # every level except `xhigh`; sending it returns a 400, which is a worse
    # outcome than running at the model's own default and saying so.
    if effort in EFFORT_UNSUPPORTED.get(model, set()):
        return None
    return effort


def image_input_tokens(width: int, height: int) -> int:
    """Roughly what a reference image costs to send, in input tokens.

    Anthropic documents ~(w x h)/750 for Claude; OpenAI bills images by patch
    count, which is a different formula with a similar magnitude. One
    approximation is used for both because the whole input side is ~1% of a
    run's cost here — being exact about a term that small would buy nothing,
    while omitting it entirely (the alternative) would quietly under-quote
    every trace.
    """
    if width <= 0 or height <= 0:
        return 0
    return int((width * height) / 750)


def estimate_cost(
    model: str,
    effort: str | None,
    max_tokens: int | None,
    extra_input_tokens: int = 0,
) -> dict:
    """Typical and worst-case dollars for one call.

    Returns ``{typical, ceiling, fraction, effort, priced}``. ``priced`` is
    False for a model with no entry in MODEL_PRICING — callers should say
    "no estimate" rather than render $0.00, which reads as "free".
    """
    price = MODEL_PRICING.get(model)
    # No default: a budget we cannot read must not be quoted as some other
    # number. `priced: False` makes the caller say so instead.
    budget = coerce_budget(max_tokens)
    if not price or not budget:
        return {
            "typical": 0.0,
            "ceiling": 0.0,
            "fraction": 0.0,
            "effort": None,
            "budget": budget or 0,
            "priced": False,
            # Which of the two reasons, so a caller can say the useful one.
            "reason": "budget" if not budget else "model",
        }

    in_price, out_price = price
    applied = resolve_effort(model, effort)
    # An unsent effort means the model's own default, which is `high`-like.
    fraction = EFFORT_UTILISATION.get(applied or "none", 0.70)

    fixed_input = (
        (_APPROX_INPUT_TOKENS + max(0, extra_input_tokens)) * in_price / 1_000_000
    )
    ceiling = fixed_input + budget * out_price / 1_000_000
    typical = fixed_input + budget * fraction * out_price / 1_000_000
    return {
        "typical": typical,
        "ceiling": ceiling,
        "fraction": fraction,
        "effort": applied,
        # The budget AS PARSED — callers render this rather than re-reading
        # the raw control, so the number in the label is the number that was
        # priced and, through the same helper, the number that gets sent.
        "budget": budget,
        "priced": True,
        "reason": None,
    }


def format_money(amount: float) -> str:
    """Dollars at a precision that does not round a real cost to $0.00."""
    if amount >= 1:
        return f"${amount:,.2f}"
    if amount >= 0.01:
        return f"${amount:.2f}"
    return f"${amount:.3f}"


# ---------------------------------------------------------------------------
#  Which of these models the deployment can actually use
# ---------------------------------------------------------------------------
#
# The tables above are a static list of what this page KNOWS how to price and
# drive. They are not a statement about what a given API key is entitled to
# call, and offering a model the key cannot use turns a click into a provider
# error the page cannot explain.
#
# So the offered list is the table intersected with what the key reports from
# `GET /v1/models`. Three things about that intersection are deliberate:
#
# 1. ALIAS-AWARE, because a naive `in` is wrong here. MEASURED 2026-09-10: the
#    endpoint lists `claude-haiku-4-5-20251001` while the table (and every
#    working call this page has ever made) uses the alias `claude-haiku-4-5`.
#    A literal set-intersection would have removed a model that demonstrably
#    works. A table id counts as available if the endpoint lists it verbatim
#    OR lists it with an 8-digit date suffix.
# 2. LAZY AND CACHED, not called at import. A network round trip at module
#    import would slow every boot, fail every offline test, and make the docs
#    site's start-up depend on a third party being reachable.
# 3. FAIL-SOFT. No key, no network, a 500 from the provider — the page still
#    works and still offers the full table, marked UNVERIFIED. A verification
#    step that can take the page down is worse than the problem it solves.
_AVAILABILITY_CACHE: dict[str, tuple[list[str], bool]] = {}

# How long an id has to be after the alias to count as a dated snapshot.
_DATE_SUFFIX_LEN = 8


def _matches(table_id: str, reported: set[str]) -> bool:
    """Is `table_id` callable given what the endpoint listed?"""
    if table_id in reported:
        return True
    prefix = f"{table_id}-"
    for r in reported:
        if r.startswith(prefix):
            rest = r[len(prefix):]
            if len(rest) == _DATE_SUFFIX_LEN and rest.isdigit():
                return True
    return False


def _reported_claude_models(timeout: float = 6.0) -> set[str] | None:
    """Model ids this deployment's Anthropic key can see, or None if unknown."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=0)
        return {m.id for m in client.models.list(limit=100)}
    except Exception:  # noqa: BLE001 - any failure means "unknown", never fatal
        return None


def available_models(
    models: list[dict], provider: str = "claude", refresh: bool = False
) -> tuple[list[dict], bool]:
    """`(offered, verified)` — the table filtered by what the key can call.

    `verified` False means the check could not run; the caller should offer the
    full table and SAY it is unverified rather than imply it was checked.
    """
    if not refresh and provider in _AVAILABILITY_CACHE:
        ids, verified = _AVAILABILITY_CACHE[provider]
        if not verified:
            return list(models), False
        return [m for m in models if m["value"] in ids], True

    reported = _reported_claude_models() if provider == "claude" else None
    if reported is None:
        _AVAILABILITY_CACHE[provider] = ([], False)
        return list(models), False

    offered = [m for m in models if _matches(m["value"], reported)]
    # Never return an empty selector: if the intersection wipes the table out,
    # something is wrong with the check rather than with every model at once.
    if not offered:
        _AVAILABILITY_CACHE[provider] = ([], False)
        return list(models), False

    _AVAILABILITY_CACHE[provider] = ([m["value"] for m in offered], True)
    return offered, True


def settle(model: str, meta: dict | None) -> float:
    """Record what a finished call actually cost. Returns the amount.

    Settlement is separate from admission on purpose: admission has to guess
    from `max_tokens`, settlement knows. Called exactly ONCE per call — and
    for a streamed run, once per RUN rather than once per element, or a
    forty-shape scene would be billed against the budget forty times.
    """
    if not meta:
        return 0.0
    price = MODEL_PRICING.get(model)
    if not price:
        # No price on file: recording zero is honest (we do not know) and is
        # why `admit` still refuses once the ceiling is reached regardless of
        # model — an unpriced model cannot be allowed to spend freely just
        # because this app cannot count it.
        return 0.0
    cost = (
        meta.get("input_tokens", 0) * price[0]
        + meta.get("output_tokens", 0) * price[1]
    ) / 1_000_000
    spend.record(cost)
    return cost


def admit(model: str, max_tokens, effort: str | None) -> None:
    """Refuse a call that would take the day past the owner's ceiling.

    Raises `spend.CeilingReached`, which the pages render as a plain message.
    Called before the request is built, so a refusal costs nothing at all.
    """
    estimate = estimate_cost(model, effort, max_tokens)
    spend.check(estimate["typical"] if estimate["priced"] else 0.0)


def _call_claude(
    model: str,
    user_prompt: str,
    max_tokens: int | None = None,
    effort: str | None = None,
) -> tuple:
    """Streaming Claude call with prompt caching on the system block.

    Returns (text, meta). `meta` carries what a benchmark needs — token
    counts, the settings actually used, and stop_reason — because the point of
    varying effort and budget is comparing the results, and a bare string
    cannot be compared.

    We stream — even though we wait for the full response — because the
    non-streaming endpoint has a synchronous HTTP deadline the SDK treats
    as a hard timeout. At `max_tokens` in the 30K–128K range on Opus /
    Sonnet that deadline routinely trips; streaming lifts that constraint
    and lets the model run to its natural end.
    """
    import anthropic

    # Falls back to the model's own default rather than raising. This is the
    # PAID path: an unreadable box should send a known-safe budget, not an
    # error after the user has already committed to spending. Coerced BEFORE
    # the ceiling check so the admission prices the budget that will be sent.
    max_tokens = coerce_budget(max_tokens, CLAUDE_MAX_TOKENS.get(model, 32000))
    admit(model, max_tokens, effort)

    client = anthropic.Anthropic()

    # Resolve effort: the caller's choice, falling back to the per-model
    # default. "none" is a real choice, not a missing value — it means send
    # no output_config so the model's own default applies.
    requested_effort = (
        effort if effort is not None else (CLAUDE_EFFORT.get(model) or "none")
    )
    # One resolver, shared with the cost label. If this request dropped a level
    # the estimate had priced in, the number the user agreed to spend and the
    # request they actually sent would disagree.
    applied_effort = resolve_effort(model, requested_effort)

    kwargs = {}
    if applied_effort:
        kwargs["output_config"] = {"effort": applied_effort}

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
            f"Truncated: hit the {max_tokens:,}-token budget mid-response, so "
            f"the JSON is incomplete. On a thinking model this budget covers "
            f"thinking AND output, so raise it (or lower effort) for a scene "
            f"this size. On /benchmark this is a real data point, not a bug: "
            f"it marks where the budget stops being sufficient for this prompt."
        )
    usage = getattr(final, "usage", None)
    meta = {
        "model": model,
        "effort": applied_effort or "none",
        "effort_ignored": bool(
            requested_effort
            and requested_effort != "none"
            and resolve_effort(model, requested_effort) is None
        ),
        "max_tokens": max_tokens,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "stop_reason": stop_reason,
    }
    settle(model, meta)
    return text, meta


def _call_openai(
    model: str,
    user_prompt: str,
    max_tokens: int | None = None,
    effort: str | None = None,
) -> tuple:
    """ChatGPT call. Same `(text, meta)` contract as `_call_claude`.

    Uses the RESPONSES endpoint rather than chat completions: these models
    take reasoning as `reasoning={"effort": ...}`, the budget as
    `max_output_tokens`, and the system prompt as `instructions` — one field
    each, where chat completions would need `reasoning_effort` plus a system
    message plus `max_completion_tokens`. Both endpoints serve these models;
    this one maps onto the page's three controls without translation.

    The meta dict mirrors `_call_claude`'s exactly, because /benchmark prices
    and renders a Claude cell and a ChatGPT cell through the same code.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on the env
        raise RuntimeError(
            "openai is not installed. `pip install 'dash-excalidraw[ai]'` "
            "or `pip install openai`."
        ) from exc

    # CHATGPT_API_KEY is this site's name for it; OPENAI_API_KEY is the SDK's
    # own convention and is accepted as a fallback so a machine that already
    # has one exported does not need a second copy under a different name.
    key = os.environ.get("CHATGPT_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "No ChatGPT key. Set CHATGPT_API_KEY (or OPENAI_API_KEY) in .env."
        )

    # The same fallback as the Claude path, and for the same reason: this is
    # the PAID path, so an unreadable control sends a known-safe budget rather
    # than raising after the user has committed to spending.
    max_tokens = coerce_budget(max_tokens, OPENAI_MAX_TOKENS.get(model, 24000))
    admit(model, max_tokens, effort)

    client = OpenAI(api_key=key)

    requested_effort = (
        effort if effort is not None else (MODEL_EFFORT.get(model) or "none")
    )
    # One resolver, shared with the cost label — see `_call_claude`.
    applied_effort = resolve_effort(model, requested_effort)

    kwargs = {}
    if applied_effort:
        kwargs["reasoning"] = {"effort": applied_effort}

    resp = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=user_prompt,
        max_output_tokens=max_tokens,
        **kwargs,
    )

    # Truncation is a STATUS here, not an exception and not a stop_reason:
    # the call returns 200 with `status="incomplete"`. Surfacing it beats
    # handing _parse_and_normalize a half-written JSON object, which fails
    # several frames from the cause. Same treatment as Claude's max_tokens.
    status = getattr(resp, "status", None)
    if status == "incomplete":
        reason = getattr(getattr(resp, "incomplete_details", None), "reason", None)
        if reason == "max_output_tokens":
            raise ValueError(
                f"Truncated: hit the {max_tokens:,}-token budget mid-response, so "
                f"the JSON is incomplete. This budget covers reasoning AND output, "
                f"so raise it (or lower effort) for a scene this size. On "
                f"/benchmark this is a real data point, not a bug."
            )
        raise ValueError(f"ChatGPT returned an incomplete response ({reason}).")

    text = getattr(resp, "output_text", "") or ""
    usage = getattr(resp, "usage", None)
    meta = {
        "model": model,
        "effort": applied_effort or "none",
        "effort_ignored": False,  # every model in OPENAI_MODELS accepts effort
        "max_tokens": max_tokens,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        # No cache-read field on this endpoint's usage object. Reported as 0
        # rather than omitted so the two providers' metas stay the same shape.
        "cache_read": 0,
        "stop_reason": status,
    }
    settle(model, meta)
    return text, meta


def call_model(
    model: str,
    user_prompt: str,
    max_tokens: int | None = None,
    effort: str | None = None,
) -> tuple:
    """Dispatch by model id. This is what makes a cross-provider comparison
    possible: /benchmark hands it a list of model ids and never has to know
    which company answers."""
    provider = PROVIDER_OF.get(model)
    if provider == "chatgpt":
        return _call_openai(model, user_prompt, max_tokens, effort)
    if provider == "claude":
        return _call_claude(model, user_prompt, max_tokens, effort)
    # Gemini lands here on purpose. It is reachable through `_call_gemini`
    # with its own signature; it is not comparable, and raising says so
    # rather than returning a cell with no cost and no matched settings.
    raise ValueError(
        f"{model} cannot be run as a comparison cell — it has no budget/effort "
        "controls or no published price. See COMPARABLE_MODELS."
    )


def _delta_text(event) -> str:
    """Text out of one streaming event, whichever provider produced it.

    Written defensively rather than against an exact event-type string: both
    SDKs emit a dozen event kinds and only some carry text, the names differ
    between them, and a missed rename would show up as a canvas that never
    updates rather than as an error. Anything with a string `.delta` (OpenAI)
    or a `.delta.text` (Anthropic) is text; everything else is skipped.
    """
    delta = getattr(event, "delta", None)
    if isinstance(delta, str):
        return delta
    text = getattr(delta, "text", None)
    return text if isinstance(text, str) else ""


def _normalize_streamed(element: Any, seen_ids: set) -> dict | None:
    """Make one streamed element safe to hand straight to the canvas.

    THE REGRESSION THIS FIXES. The blocking path ran the whole response
    through `_parse_and_normalize` -> `_coerce_types`, which fills in the
    fields Excalidraw needs (`version`, `versionNonce`, `seed`, `isDeleted`,
    `updated`) and turns stringified numbers back into numbers. Streaming
    dispatched raw model output to `updateScene` instead and skipped all of
    it, so the two paths disagreed about what an element is.

    AND THE DUPLICATE ID, which is the one that looks like magic. `updateScene`
    reconciles BY ID: an incoming element whose id already exists REPLACES the
    existing one rather than joining it. A model that repeats ids — which they
    do once a scene gets long, especially after restarting a numbering scheme —
    therefore makes the canvas delete one shape for every shape it adds, and
    the element count plateaus instead of growing. Renaming the duplicate is
    what keeps both shapes.
    """
    if not isinstance(element, dict):
        return None
    element_id = element.get("id")
    if not isinstance(element_id, str) or not element_id or element_id in seen_ids:
        element_id = f"el-{uuid.uuid4().hex[:12]}"
    seen_ids.add(element_id)
    normalized = _coerce_types({**element, "id": element_id})
    return normalized if isinstance(normalized, dict) else None


def stream_model(
    model: str,
    user_prompt: str,
    max_tokens: int | None = None,
    effort: str | None = None,
    image: tuple[str, str] | None = None,
    system: str | None = None,
):
    """Yield `("element", dict)` as each element completes, then `("done", meta)`.

    This is the difference between a spinner and watching it draw. The call
    already streamed — `_call_claude` has always used `messages.stream()` to
    dodge the non-streaming HTTP deadline — but it threw the intermediate
    text away and parsed once at the end. Here the deltas go through
    ElementStreamParser instead, so a shape reaches the canvas as soon as its
    closing brace arrives rather than when the last one does.

    Errors are raised, not yielded: a caller that is mid-draw needs to stop,
    and the pages already surface an exception as a status line.
    """
    provider = PROVIDER_OF.get(model)
    # Refused HERE rather than at the provider: a model that cannot see would
    # otherwise be sent an image it silently ignores and would trace from the
    # prompt alone, producing a confident drawing of nothing in particular.
    if image and model not in VISION_MODELS:
        raise ValueError(f"{model} does not accept image input.")

    # ONE admission per run, here, before any connection is opened — not per
    # element. The budget is charged once at the end by `settle`, for the same
    # reason: a forty-shape scene is one call, not forty.
    budget_for_admission = coerce_budget(
        max_tokens, MODEL_MAX_TOKENS.get(model, 32000)
    )
    admit(model, budget_for_admission, effort)

    parser = ElementStreamParser()
    # Shared across the whole run: a duplicate id anywhere in the scene costs
    # a shape, not just a duplicate of the one before it.
    seen_ids: set = set()

    if provider == "claude":
        import anthropic

        client = anthropic.Anthropic()
        budget = coerce_budget(max_tokens, CLAUDE_MAX_TOKENS.get(model, 32000))
        requested = effort if effort is not None else (MODEL_EFFORT.get(model) or "none")
        applied = resolve_effort(model, requested)
        kwargs = {"output_config": {"effort": applied}} if applied else {}

        if image:
            media_type, b64 = image
            # Image FIRST: the instruction that follows then refers to
            # something the model has already looked at.
            content = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64,
                    },
                },
                {"type": "text", "text": user_prompt},
            ]
        else:
            content = user_prompt

        with client.messages.stream(
            model=model,
            max_tokens=budget,
            system=[
                {
                    "type": "text",
                    "text": system or SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": content}],
            **kwargs,
        ) as stream:
            for event in stream:
                for element in parser.feed(_delta_text(event)):
                    normalized = _normalize_streamed(element, seen_ids)
                    if normalized is not None:
                        yield ("element", normalized)
            final = stream.get_final_message()

        stop = getattr(final, "stop_reason", None)
        if stop == "refusal":
            details = getattr(final, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise ValueError(
                "Claude's safety classifiers declined this request"
                + (f" (category: {category})" if category else "")
                + ". Nothing was generated."
            )
        usage = getattr(final, "usage", None)
        meta = {
            "model": model,
            "effort": applied or "none",
            "effort_ignored": bool(
                requested and requested != "none" and model not in EFFORT_CAPABLE
            ),
            "max_tokens": budget,
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "stop_reason": stop,
        }
        settle(model, meta)
        yield ("done", meta)
        return

    if provider != "chatgpt":
        raise ValueError(f"{model} cannot be streamed — see COMPARABLE_MODELS.")

    from openai import OpenAI

    key = os.environ.get("CHATGPT_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("No ChatGPT key. Set CHATGPT_API_KEY in .env.")
    client = OpenAI(api_key=key)
    budget = coerce_budget(max_tokens, OPENAI_MAX_TOKENS.get(model, 24000))
    requested = effort if effort is not None else (MODEL_EFFORT.get(model) or "none")
    applied = resolve_effort(model, requested)
    kwargs = {"reasoning": {"effort": applied}} if applied else {}

    if image:
        media_type, b64 = image
        request_input = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_image",
                        "image_url": f"data:{media_type};base64,{b64}",
                        "detail": "high",
                    },
                    {"type": "input_text", "text": user_prompt},
                ],
            }
        ]
    else:
        request_input = user_prompt

    with client.responses.stream(
        model=model,
        instructions=system or SYSTEM_PROMPT,
        input=request_input,
        max_output_tokens=budget,
        **kwargs,
    ) as stream:
        for event in stream:
            for element in parser.feed(_delta_text(event)):
                normalized = _normalize_streamed(element, seen_ids)
                if normalized is not None:
                    yield ("element", normalized)
        final = stream.get_final_response()

    # Truncation is REPORTED here, not raised — unlike the non-streaming
    # `_call_openai`, which raises because it has nothing to show. By this
    # point the elements that did arrive are already on the canvas and are
    # perfectly good shapes; turning that into an exception would present a
    # partial success as a failure. The page names the budget in the status.
    status = getattr(final, "status", None)
    usage = getattr(final, "usage", None)
    meta = {
        "model": model,
        "effort": applied or "none",
        "effort_ignored": False,
        "max_tokens": budget,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read": 0,
        "stop_reason": status,
    }
    settle(model, meta)
    yield ("done", meta)


def _call_gemini(model: str, user_prompt: str) -> str:
    """Gemini call with a generous output budget and JSON mime-type hint."""
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError as exc:
        raise RuntimeError(
            "google-genai is not installed. `pip install google-genai`."
        ) from exc

    # Gemini is priced now, so it is admitted like any other paid call and
    # settled below. It takes no effort parameter and its budget is fixed, so
    # the estimate uses GEMINI_MAX_TOKENS and no effort.
    admit(model, GEMINI_MAX_TOKENS, None)

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

    # Settle from the usage the response carries. Gemini names the fields
    # differently from the other two, so they are mapped onto the same shape
    # `settle` expects rather than teaching `settle` a third vocabulary.
    usage = getattr(resp, "usage_metadata", None)
    settle(
        model,
        {
            "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
            "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        },
    )
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
