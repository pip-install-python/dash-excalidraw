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
EFFORT_CAPABLE = {"claude-opus-5", "claude-opus-4-7", "claude-sonnet-4-6"}

# USD per 1M tokens (input, output), for the cost estimate in the status line.
# A LOCAL ESTIMATE, not a bill: it ignores cache-write premiums and every
# discount, and published prices change. It is here so a benchmark sweep can
# be compared on cost as well as latency, which is the whole point of being
# able to vary effort and budget.
CLAUDE_PRICING = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

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


def _call_claude(
    model: str,
    user_prompt: str,
    max_tokens: int | None = None,
    effort: str | None = None,
) -> tuple:
    """Returns (text, meta). `meta` carries what a benchmark needs — token
    counts, the settings actually used, and stop_reason — because the point of
    varying effort and budget is comparing the results, and a bare string
    cannot be compared."""
    """Streaming Claude call with prompt caching on the system block.

    We stream — even though we wait for the full response — because the
    non-streaming endpoint has a synchronous HTTP deadline the SDK treats
    as a hard timeout. At `max_tokens` in the 30K–128K range on Opus /
    Sonnet that deadline routinely trips; streaming lifts that constraint
    and lets the model run to its natural end.
    """
    import anthropic

    client = anthropic.Anthropic()
    max_tokens = int(max_tokens or CLAUDE_MAX_TOKENS.get(model, 32000))

    # Resolve effort: the caller's choice, falling back to the per-model
    # default. "none" is a real choice, not a missing value — it means send
    # no output_config so the model's own default applies.
    if effort is None:
        effort = CLAUDE_EFFORT.get(model) or "none"
    applied_effort = effort if (effort != "none" and model in EFFORT_CAPABLE) else None

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
            effort and effort != "none" and model not in EFFORT_CAPABLE
        ),
        "max_tokens": max_tokens,
        "input_tokens": getattr(usage, "input_tokens", 0) or 0,
        "output_tokens": getattr(usage, "output_tokens", 0) or 0,
        "cache_read": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "stop_reason": stop_reason,
    }
    return text, meta


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
