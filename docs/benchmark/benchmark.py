"""Run one prompt across several settings at once and compare the results.

The /ai-agent page answers "can it draw this?". This page answers the question
you actually have afterwards: "what do I give up by turning this knob down?"
— which needs the same prompt rendered several ways, side by side, with the
cost of each.

THREE THINGS THAT SHAPE THE DESIGN
1. Variants run CONCURRENTLY. They are network-bound, so a six-cell matrix
   costs roughly one generation's wall time instead of six. Run serially, a
   sweep takes long enough that nobody runs a second one.
2. The cost is shown BEFORE you press the button, not after. A six-cell Opus 5
   matrix is real money, and an estimate that arrives with the results is an
   apology rather than a decision.
3. Every cell renders its own canvas in view mode. Element counts and token
   totals rank the runs; only looking at them tells you whether the extra
   tokens bought anything.
"""

from __future__ import annotations

import concurrent.futures
import time
import uuid

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, html, no_update

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame
from lib.scene_ai import (
    CLAUDE_EFFORT,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODELS,
    CLAUDE_PRICING,
    EFFORT_CAPABLE,
    _call_claude,
    _parse_and_normalize,
    _spend_allowed,
)

# Kept small on purpose. Every extra cell is another paid call, and the point
# of the page is comparison, not exhaustiveness — beyond about six panels you
# stop being able to see them at a glance, which is the whole feature.
MAX_VARIANTS = 6

EFFORT_CHOICES = ["none", "low", "medium", "high", "xhigh", "max"]
BUDGET_CHOICES = ["4000", "8000", "16000", "24000", "48000", "64000"]


def _estimate(model: str, budget: int, n: int) -> float:
    """Rough worst-case dollar estimate for a run of `n` variants.

    Deliberately pessimistic: it prices every variant as if it used its whole
    budget. Under-promising here is the right bias — the number exists to stop
    someone accidentally spending $5, not to be accurate to the cent.
    """
    price = CLAUDE_PRICING.get(model)
    if not price:
        return 0.0
    return n * budget * price[1] / 1_000_000


def _panel(result: dict):
    """One cell: its settings, its numbers, and its drawing."""
    if result.get("error"):
        return dmc.GridCol(
            dmc.Paper(
                withBorder=True,
                p="sm",
                children=dmc.Stack(
                    gap=4,
                    children=[
                        dmc.Badge(result["label"], color="red", variant="light"),
                        dmc.Text(result["error"], size="xs", c="red"),
                    ],
                ),
            ),
            span={"base": 12, "md": 6},
        )

    m = result["meta"]
    cost = (
        m["input_tokens"] * CLAUDE_PRICING.get(result["model"], (0, 0))[0]
        + m["output_tokens"] * CLAUDE_PRICING.get(result["model"], (0, 0))[1]
    ) / 1_000_000

    return dmc.GridCol(
        dmc.Paper(
            withBorder=True,
            p="sm",
            children=dmc.Stack(
                gap="xs",
                children=[
                    dmc.Group(
                        gap="xs",
                        children=[
                            dmc.Badge(result["label"], variant="light"),
                            dmc.Badge(
                                f"{result['elements']} elements",
                                color="violet",
                                variant="light",
                            ),
                            dmc.Badge(
                                f"{result['seconds']:.0f}s", color="gray", variant="light"
                            ),
                            dmc.Badge(
                                f"~${cost:.3f}", color="teal", variant="light"
                            ),
                        ],
                    ),
                    dmc.Text(
                        f"{m['output_tokens']:,} out / {m['input_tokens']:,} in"
                        + (
                            f"  ·  stop={m['stop_reason']}"
                            if m["stop_reason"] != "end_turn"
                            else ""
                        ),
                        size="xs",
                        c="dimmed",
                    ),
                    canvas_frame(
                        DashExcalidraw(
                            id=result["canvas_id"],
                            height="340px",
                            # View mode: these are specimens to compare, not
                            # canvases to edit. It also stops a stray click in
                            # one panel from changing what you are comparing.
                            viewModeEnabled=True,
                            initialData={
                                "elements": result["elements_data"],
                                "appState": {"viewBackgroundColor": "#ffffff"},
                                "scrollToContent": True,
                            },
                        ),
                        min_height=340,
                    ),
                ],
            ),
        ),
        span={"base": 12, "md": 6},
    )


component = dmc.Stack(
    gap="md",
    children=[
        dmc.Alert(
            title="This page spends real API credits",
            color="yellow",
            children=(
                "Each variant is a separate paid model call. The estimate below "
                "updates as you change the matrix — check it before running."
            ),
        ),
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
                                    id="bm-model",
                                    label="Model",
                                    data=CLAUDE_MODELS,
                                    value=CLAUDE_MODELS[0]["value"],
                                ),
                                span={"base": 12, "sm": 4},
                            ),
                            dmc.GridCol(
                                dmc.SegmentedControl(
                                    id="bm-axis",
                                    data=[
                                        {"value": "effort", "label": "Vary effort"},
                                        {"value": "budget", "label": "Vary max tokens"},
                                    ],
                                    value="effort",
                                    fullWidth=True,
                                ),
                                span={"base": 12, "sm": 8},
                            ),
                        ],
                    ),
                    # Only one axis varies at a time. A grid over both is a
                    # combinatorial bill, and two variables moving at once is
                    # exactly what makes a comparison unreadable.
                    dmc.CheckboxGroup(
                        id="bm-efforts",
                        label="Effort levels to compare",
                        value=["low", "high"],
                        children=dmc.Group(
                            [dmc.Checkbox(label=e, value=e) for e in EFFORT_CHOICES],
                            gap="md",
                        ),
                    ),
                    dmc.CheckboxGroup(
                        id="bm-budgets",
                        label="Max-token budgets to compare",
                        value=["8000", "24000"],
                        children=dmc.Group(
                            [
                                dmc.Checkbox(label=f"{int(b):,}", value=b)
                                for b in BUDGET_CHOICES
                            ],
                            gap="md",
                        ),
                    ),
                    dmc.Grid(
                        gutter="md",
                        children=[
                            dmc.GridCol(
                                dmc.NumberInput(
                                    id="bm-fixed-budget",
                                    label="Fixed max tokens (when varying effort)",
                                    value=24000,
                                    min=1000,
                                    max=128000,
                                    step=4000,
                                ),
                                span={"base": 12, "sm": 6},
                            ),
                            dmc.GridCol(
                                dmc.Select(
                                    id="bm-fixed-effort",
                                    label="Fixed effort (when varying max tokens)",
                                    data=[
                                        {"value": e, "label": e} for e in EFFORT_CHOICES
                                    ],
                                    value="low",
                                ),
                                span={"base": 12, "sm": 6},
                            ),
                        ],
                    ),
                    dmc.Textarea(
                        id="bm-prompt",
                        label="Prompt",
                        description="The same prompt is sent to every variant — that is what makes them comparable",
                        placeholder="E.g. 'an architecture diagram of a payments service: api, ledger, queue, two databases, with retry paths'",
                        autosize=True,
                        minRows=3,
                    ),
                    dmc.Group(
                        [
                            dmc.Button(
                                "Run benchmark",
                                id="bm-run",
                            ),
                            dmc.Text(id="bm-estimate", size="sm", c="dimmed"),
                        ],
                        justify="space-between",
                    ),
                ],
            ),
        ),
        dmc.Alert(
            id="bm-status",
            title="Status",
            color="gray",
            children="Ready.",
        ),
        dcc.Loading(html.Div(id="bm-results"), type="dot"),
    ],
)


@callback(
    Output("bm-estimate", "children"),
    Input("bm-model", "value"),
    Input("bm-axis", "value"),
    Input("bm-efforts", "value"),
    Input("bm-budgets", "value"),
    Input("bm-fixed-budget", "value"),
)
def _estimate_cost(model, axis, efforts, budgets, fixed_budget):
    """Price the matrix BEFORE it runs. See the module docstring."""
    if axis == "effort":
        n = len(efforts or [])
        budget = int(fixed_budget or 24000)
    else:
        n = len(budgets or [])
        budget = max((int(b) for b in budgets or ["24000"]), default=24000)

    n = min(n, MAX_VARIANTS)
    if not n:
        return "Select at least one variant."
    est = _estimate(model, budget, n)
    return f"{n} variant{'s' if n != 1 else ''} · up to ~${est:.2f} if every one uses its full budget"


@callback(
    Output("bm-results", "children"),
    Output("bm-status", "children"),
    Output("bm-status", "color"),
    Input("bm-run", "n_clicks"),
    State("bm-model", "value"),
    State("bm-axis", "value"),
    State("bm-efforts", "value"),
    State("bm-budgets", "value"),
    State("bm-fixed-budget", "value"),
    State("bm-fixed-effort", "value"),
    State("bm-prompt", "value"),
    running=[
        (Output("bm-run", "loading"), True, False),
        (Output("bm-run", "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def _run(_clicks, model, axis, efforts, budgets, fixed_budget, fixed_effort, prompt):
    if not prompt or not prompt.strip():
        return no_update, "Write a prompt first.", "yellow"

    # Same gate as /ai-agent, and it matters more here: one click is up to six
    # paid calls. See lib/scene_ai._spend_allowed.
    if not _spend_allowed():
        return (
            no_update,
            "Sign in to run a benchmark — this page spends real API credits.",
            "yellow",
        )

    if axis == "effort":
        variants = [
            (e, int(fixed_budget or 24000)) for e in (efforts or [])[:MAX_VARIANTS]
        ]
    else:
        variants = [
            (fixed_effort or "low", int(b)) for b in (budgets or [])[:MAX_VARIANTS]
        ]

    if not variants:
        return no_update, "Select at least one variant to compare.", "yellow"

    if model not in EFFORT_CAPABLE:
        # Varying effort on a model that rejects the parameter would run N
        # identical calls and present them as a comparison — worse than an
        # error, because the output looks like a result.
        if axis == "effort" and len({e for e, _ in variants}) > 1:
            return (
                no_update,
                f"{model} does not accept the effort parameter, so every variant "
                "would be identical. Switch to varying max tokens, or pick "
                "another model.",
                "red",
            )

    started = time.monotonic()
    run_id = uuid.uuid4().hex[:8]

    def one(index_variant):
        index, (effort, budget) = index_variant
        label = f"effort={effort} · {budget:,} tok"
        try:
            raw, meta = _call_claude(model, prompt.strip(), budget, effort)
            parsed = _parse_and_normalize(raw)
            elements = parsed.get("elements", [])
            return {
                "label": label,
                "model": model,
                "meta": meta,
                "elements": len(elements),
                "elements_data": elements,
                "seconds": 0.0,
                "canvas_id": f"bm-canvas-{run_id}-{index}",
            }
        except Exception as exc:  # one bad variant must not lose the others
            return {"label": label, "error": f"{type(exc).__name__}: {exc}"}

    # Concurrent on purpose — see the module docstring. Bounded by the variant
    # count, which MAX_VARIANTS already caps.
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(variants)) as pool:
        futures = {
            pool.submit(one, (i, v)): i for i, v in enumerate(variants)
        }
        per_start = time.monotonic()
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            r["seconds"] = time.monotonic() - per_start
            results.append((futures[fut], r))

    results = [r for _, r in sorted(results, key=lambda x: x[0])]

    elapsed = time.monotonic() - started
    ok = [r for r in results if not r.get("error")]
    total_cost = sum(
        (
            r["meta"]["input_tokens"] * CLAUDE_PRICING.get(model, (0, 0))[0]
            + r["meta"]["output_tokens"] * CLAUDE_PRICING.get(model, (0, 0))[1]
        )
        / 1_000_000
        for r in ok
    )
    serial = sum(r["seconds"] for r in ok)

    status = (
        f"{len(ok)}/{len(results)} variants in {elapsed:.0f}s "
        f"(≈{serial:.0f}s if run one at a time) · ~${total_cost:.3f} total"
    )
    grid = dmc.Grid(gutter="md", children=[_panel(r) for r in results])
    return grid, status, "green" if len(ok) == len(results) else "yellow"
