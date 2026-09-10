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
    COMPARABLE_MODELS,
    EFFORT_CAPABLE,
    MODEL_LABEL,
    MODEL_PRICING,
    _parse_and_normalize,
    _spend_allowed,
    call_model,
    coerce_budget,
    estimate_cost,
    format_money,
)

# Kept small on purpose. Every extra cell is another paid call, and the point
# of the page is comparison, not exhaustiveness — beyond about six panels you
# stop being able to see them at a glance, which is the whole feature.
MAX_VARIANTS = 6

EFFORT_CHOICES = ["none", "low", "medium", "high", "xhigh", "max"]
BUDGET_CHOICES = ["4000", "8000", "16000", "24000", "48000", "64000"]


def _variants(
    model, axis, efforts, budgets, models, fixed_budget, fixed_effort
) -> list[tuple]:
    """The exact `(model, effort, budget)` list a run will execute.

    Shared by the estimate and the runner on purpose. The old estimate priced
    `n` variants at the LARGEST selected budget, which over-quoted every
    budget sweep — a 4K+8K+16K comparison was billed as three times 16K. It
    also ignored effort entirely, so the control the page exists to explore
    made no difference to the number above the button. Building the real list
    once fixes both, and means the quote cannot drift from the run.

    MODEL IS PER-VARIANT, not a single value alongside, because the third axis
    compares models across providers — a Claude cell and a ChatGPT cell in one
    sweep. The other two axes just repeat the one selected model.

    coerce_budget, not int(): `bm-fixed-budget` is a NumberInput and hands over
    whatever is in the box mid-edit ("64.000" crashed the estimate on
    /ai-agent). The chips are our own strings and always parse, but they go
    through the same door so there is one rule.
    """
    if axis == "effort":
        budget = coerce_budget(fixed_budget, 24000)
        return [(model, e, budget) for e in (efforts or [])[:MAX_VARIANTS]]
    if axis == "model":
        budget = coerce_budget(fixed_budget, 24000)
        effort = fixed_effort or "low"
        return [(m, effort, budget) for m in (models or [])[:MAX_VARIANTS]]
    return [
        (model, fixed_effort or "low", coerce_budget(b, 24000))
        for b in (budgets or [])[:MAX_VARIANTS]
    ]


def _variant_label(axis: str, model: str, effort: str, budget: int) -> str:
    """What a panel calls itself. On the model axis the model IS the finding,
    so it leads; elsewhere it is constant across cells and only clutters."""
    if axis == "model":
        return f"{MODEL_LABEL.get(model, model)} · effort={effort}"
    return f"effort={effort} · {budget:,} tok"


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
        m["input_tokens"] * MODEL_PRICING.get(result["model"], (0, 0))[0]
        + m["output_tokens"] * MODEL_PRICING.get(result["model"], (0, 0))[1]
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
                                    data=COMPARABLE_MODELS,
                                    value=COMPARABLE_MODELS[0]["value"],
                                ),
                                id="bm-model-col",
                                span={"base": 12, "sm": 4},
                            ),
                            dmc.GridCol(
                                dmc.SegmentedControl(
                                    id="bm-axis",
                                    data=[
                                        {"value": "effort", "label": "Vary effort"},
                                        {"value": "budget", "label": "Vary max tokens"},
                                        {"value": "model", "label": "Compare models"},
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
                    #
                    # ONLY THE ACTIVE AXIS IS SHOWN. Both lists used to render
                    # together, always enabled, while the segmented control
                    # above decided which one the run actually read — so
                    # ticking "Max-token budgets to compare" while the axis sat
                    # on its "Vary effort" default changed nothing, including
                    # the price. The estimate was right and the page was
                    # lying: it offered an input it then ignored. Hiding the
                    # inactive pair is the fix, not making the price react to
                    # a control the run does not read.
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
                        style={"display": "none"},  # axis defaults to "effort"
                        children=dmc.Group(
                            [
                                dmc.Checkbox(label=f"{int(b):,}", value=b)
                                for b in BUDGET_CHOICES
                            ],
                            gap="md",
                        ),
                    ),
                    # The cross-provider axis. Every entry here accepts a
                    # budget and an effort and has a published price, so a
                    # Claude cell and a ChatGPT cell are genuinely comparable:
                    # same prompt, same budget, same effort, and a cost on
                    # each. Gemini is deliberately absent — see
                    # COMPARABLE_MODELS in lib/scene_ai.py.
                    dmc.MultiSelect(
                        id="bm-models",
                        label="Models to compare",
                        description=(
                            "Mix providers freely — the same prompt, budget and "
                            "effort go to each"
                        ),
                        data=COMPARABLE_MODELS,
                        value=["claude-opus-5", "gpt-6-astra"],
                        maxValues=MAX_VARIANTS,
                        clearable=True,
                        style={"display": "none"},  # axis defaults to "effort"
                    ),
                    dmc.Grid(
                        gutter="md",
                        children=[
                            dmc.GridCol(
                                dmc.NumberInput(
                                    id="bm-fixed-budget",
                                    label="Max tokens (held constant)",
                                    description="Every effort variant runs at this budget",
                                    value=24000,
                                    min=1000,
                                    max=128000,
                                    step=4000,
                                ),
                                id="bm-fixed-budget-col",
                                span={"base": 12, "sm": 6},
                            ),
                            dmc.GridCol(
                                dmc.Select(
                                    id="bm-fixed-effort",
                                    label="Effort (held constant)",
                                    description="Every budget variant runs at this effort",
                                    data=[
                                        {"value": e, "label": e} for e in EFFORT_CHOICES
                                    ],
                                    value="low",
                                ),
                                id="bm-fixed-effort-col",
                                span={"base": 12, "sm": 6},
                                style={"display": "none"},  # axis defaults to "effort"
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
    Output("bm-efforts", "style"),
    Output("bm-budgets", "style"),
    Output("bm-models", "style"),
    Output("bm-model-col", "style"),
    Output("bm-fixed-budget-col", "style"),
    Output("bm-fixed-effort-col", "style"),
    Input("bm-axis", "value"),
)
def _show_active_axis(axis):
    """Show only the controls the run will actually read.

    The segmented control decides which list becomes the variants and which
    values are held constant; everything else is inert. Leaving it all on
    screen made the inert controls look live — tick three budgets while the
    axis says "Vary effort" and nothing happens, price included.

    Note the single Model select disappears on the model axis: there, the
    model is the thing being varied, so one fixed model would be a control
    that contradicts the axis.
    """
    shown: dict = {}
    hidden = {"display": "none"}

    def vis(active: bool):
        return shown if active else hidden

    return (
        vis(axis == "effort"),  # effort levels to compare
        vis(axis == "budget"),  # max-token budgets to compare
        vis(axis == "model"),  # models to compare (cross-provider)
        vis(axis != "model"),  # the single model select
        vis(axis != "budget"),  # the budget held constant
        vis(axis != "effort"),  # the effort held constant
    )


@callback(
    Output("bm-estimate", "children"),
    Input("bm-model", "value"),
    Input("bm-axis", "value"),
    Input("bm-efforts", "value"),
    Input("bm-budgets", "value"),
    Input("bm-models", "value"),
    Input("bm-fixed-budget", "value"),
    Input("bm-fixed-effort", "value"),
)
def _estimate_cost(model, axis, efforts, budgets, models, fixed_budget, fixed_effort):
    """Price the matrix BEFORE it runs, per variant. See the module docstring.

    One click here is up to six paid calls, so this number is the last thing
    between a curious click and a real bill. It prices each variant at its own
    effort and its own budget — the two things the page lets you vary — and
    shows the ceiling beside the typical figure, because `max_tokens` bounds
    the spend but does not determine it.
    """
    variants = _variants(
        model, axis, efforts, budgets, models, fixed_budget, fixed_effort
    )
    if not variants:
        return "Select at least one variant."

    ests = [(m, estimate_cost(m, e, b)) for m, e, b in variants]
    unpriced = sorted({m for m, x in ests if not x["priced"]})
    if unpriced:
        return f"{len(variants)} variants · no price on file for {', '.join(unpriced)}."

    typical = sum(x["typical"] for _, x in ests)
    ceiling = sum(x["ceiling"] for _, x in ests)
    n = len(variants)

    # Name the axis in the number. Three controls can each produce "3
    # variants", and when the price surprises someone the first useful fact is
    # which of them the run is actually reading.
    sweeping = {"effort": "effort", "budget": "max tokens", "model": "models"}[axis]
    head = (
        f"{n} variant{'s' if n != 1 else ''} varying {sweeping} · about "
        f"{format_money(typical)} for the sweep, at most "
        f"{format_money(ceiling)} if every one runs its budget out."
    )

    # Where the cells differ in price, the spread is the interesting part: a
    # single total hides which one is doing the spending. That is most acute
    # on the model axis, where rates differ by up to 40x between providers.
    if n > 1 and axis in ("budget", "model"):
        lo = min(ests, key=lambda pair: pair[1]["typical"])
        hi = max(ests, key=lambda pair: pair[1]["typical"])
        if axis == "model":
            head += (
                f" Cheapest {MODEL_LABEL.get(lo[0], lo[0])} "
                f"~{format_money(lo[1]['typical'])}, dearest "
                f"{MODEL_LABEL.get(hi[0], hi[0])} "
                f"~{format_money(hi[1]['typical'])}."
            )
        else:
            head += (
                f" Cheapest cell ~{format_money(lo[1]['typical'])}, "
                f"dearest ~{format_money(hi[1]['typical'])}."
            )

    # Only meaningful when one model spans the sweep; on the model axis the
    # per-model note would be ambiguous, and the estimate already prices each
    # cell correctly either way.
    if axis != "model" and model not in EFFORT_CAPABLE:
        head += " (This model ignores effort, so every cell costs the same.)"

    return head


@callback(
    Output("bm-results", "children"),
    Output("bm-status", "children"),
    Output("bm-status", "color"),
    Input("bm-run", "n_clicks"),
    State("bm-model", "value"),
    State("bm-axis", "value"),
    State("bm-efforts", "value"),
    State("bm-budgets", "value"),
    State("bm-models", "value"),
    State("bm-fixed-budget", "value"),
    State("bm-fixed-effort", "value"),
    State("bm-prompt", "value"),
    running=[
        (Output("bm-run", "loading"), True, False),
        (Output("bm-run", "disabled"), True, False),
    ],
    prevent_initial_call=True,
)
def _run(
    _clicks, model, axis, efforts, budgets, models, fixed_budget, fixed_effort, prompt
):
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

    # Same builder the estimate uses, so the run cannot execute a different
    # matrix from the one that was priced above the button.
    variants = _variants(
        model, axis, efforts, budgets, models, fixed_budget, fixed_effort
    )

    if not variants:
        return no_update, "Select at least one variant to compare.", "yellow"

    if axis == "effort" and model not in EFFORT_CAPABLE:
        # Varying effort on a model that rejects the parameter would run N
        # identical calls and present them as a comparison — worse than an
        # error, because the output looks like a result.
        if len({e for _, e, _ in variants}) > 1:
            return (
                no_update,
                f"{model} does not accept the effort parameter, so every variant "
                "would be identical. Switch to varying max tokens, or pick "
                "another model.",
                "red",
            )

    # The model axis has its own version of the same trap: one model selected
    # is not a comparison, it is a single call wearing a comparison's UI.
    if axis == "model" and len(variants) < 2:
        return (
            no_update,
            "Pick at least two models to compare — one is just a single run.",
            "yellow",
        )

    started = time.monotonic()
    run_id = uuid.uuid4().hex[:8]

    def one(index_variant):
        index, (variant_model, effort, budget) = index_variant
        label = _variant_label(axis, variant_model, effort, budget)
        try:
            # call_model dispatches on the model id, so a Claude cell and a
            # ChatGPT cell in the same sweep go through identical code and
            # come back with identically-shaped meta.
            raw, meta = call_model(variant_model, prompt.strip(), budget, effort)
            parsed = _parse_and_normalize(raw)
            elements = parsed.get("elements", [])
            return {
                "label": label,
                "model": variant_model,
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
    # Priced per RESULT's model, not per the page's model select — on the
    # model axis the cells are different models at different rates, and
    # pricing them all at one would be wrong by up to 40x.
    total_cost = sum(
        (
            r["meta"]["input_tokens"] * MODEL_PRICING.get(r["model"], (0, 0))[0]
            + r["meta"]["output_tokens"] * MODEL_PRICING.get(r["model"], (0, 0))[1]
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
