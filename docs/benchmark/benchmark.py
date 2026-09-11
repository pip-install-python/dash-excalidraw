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

import dash_mantine_components as dmc
from dash import ALL, Input, Output, State, callback, dcc, no_update

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame
from lib import scene_stream, spend
from lib.scene_ai import (
    CLAUDE_EFFORT,
    CLAUDE_MAX_TOKENS,
    CLAUDE_MODELS,
    COMPARABLE_MODELS,
    EFFORT_CAPABLE,
    MODEL_LABEL,
    MODEL_PRICING,
    _spend_allowed,
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


def _slot(index: int):
    """One cell's skeleton, built ONCE at import and then filled by callbacks.

    Panels used to be constructed from finished results, which is why the page
    could only show anything after every variant had returned. They are static
    now, with pattern-matching ids, so a callback can write into six canvases
    while the models are still drawing. Unused slots are hidden rather than
    absent — a component that does not exist cannot be an Output.
    """
    return dmc.GridCol(
        id={"type": "bm-slot", "index": index},
        style={"display": "none"},
        span={"base": 12, "md": 6},
        children=dmc.Paper(
            withBorder=True,
            p="sm",
            children=dmc.Stack(
                gap="xs",
                children=[
                    dmc.Box(id={"type": "bm-head", "index": index}),
                    canvas_frame(
                        DashExcalidraw(
                            id={"type": "bm-canvas", "index": index},
                            height="340px",
                            # View mode: these are specimens to compare, not
                            # canvases to edit. It also stops a stray click in
                            # one panel from changing what you are comparing.
                            viewModeEnabled=True,
                        ),
                        min_height=340,
                    ),
                ],
            ),
        ),
    )


def _cell_cost(model: str, meta: dict | None) -> float:
    if not meta:
        return 0.0
    price = MODEL_PRICING.get(model, (0, 0))
    return (
        meta["input_tokens"] * price[0] + meta["output_tokens"] * price[1]
    ) / 1_000_000


def _head(cell: dict, state: dict):
    """The badges above one cell's canvas, from whatever is known so far."""
    if state.get("error"):
        return dmc.Stack(
            gap=4,
            children=[
                dmc.Badge(cell["label"], color="red", variant="light"),
                dmc.Text(state["error"], size="xs", c="red"),
            ],
        )

    drawn = len(state.get("all", []))
    badges = [dmc.Badge(cell["label"], variant="light")]
    badges.append(
        dmc.Badge(
            f"{drawn} element{'s' if drawn != 1 else ''}",
            color="violet",
            variant="light",
        )
    )
    badges.append(
        dmc.Badge(f"{state.get('elapsed', 0.0):.0f}s", color="gray", variant="light")
    )

    meta = state.get("meta")
    if state.get("cancelled"):
        badges.append(dmc.Badge("stopped", color="orange", variant="filled"))
    elif not state.get("done"):
        badges.append(dmc.Badge("drawing…", color="blue", variant="dot"))

    if meta:
        badges.append(
            dmc.Badge(
                f"~${_cell_cost(cell['model'], meta):.3f}",
                color="teal",
                variant="light",
            )
        )

    detail = ""
    if meta:
        detail = f"{meta['output_tokens']:,} out / {meta['input_tokens']:,} in"
        stop = meta.get("stop_reason")
        if stop in ("max_tokens", "incomplete"):
            detail += f"  ·  TRUNCATED at {meta['max_tokens']:,} tokens"
        elif stop and stop not in ("end_turn", "completed"):
            detail += f"  ·  stop={stop}"
    if state.get("lost"):
        detail += f"  ·  {state['lost']} lost from the buffer"

    return dmc.Stack(
        gap=4,
        children=[
            dmc.Group(gap="xs", children=badges),
            dmc.Text(detail, size="xs", c="dimmed"),
        ],
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
                            # THE BRAKES. This page is the reason they matter
                            # most: one click is up to six paid calls running
                            # at once, so a stop here is worth six times what
                            # it is worth on /ai-agent.
                            dmc.Button(
                                "Stop all",
                                id="bm-stop",
                                leftSection="■",
                                color="red",
                                disabled=True,
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
        # Six fixed slots, hidden until used. Previously this was an empty
        # Div filled with finished panels, which is why nothing could appear
        # until everything had.
        dmc.Grid(gutter="md", children=[_slot(i) for i in range(MAX_VARIANTS)]),
        # One ticker for the whole sweep, not one per cell: six Intervals
        # would mean six callbacks a second arguing over the same Store.
        dcc.Store(id="bm-runs", data=None),
        dcc.Interval(id="bm-tick", interval=500, disabled=True),
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


BLANK = {"display": "none"}
SHOWN: dict = {}


@callback(
    Output("bm-runs", "data"),
    Output("bm-tick", "disabled"),
    Output("bm-status", "children"),
    Output("bm-status", "color"),
    Output({"type": "bm-slot", "index": ALL}, "style"),
    Output({"type": "bm-head", "index": ALL}, "children"),
    Output({"type": "bm-canvas", "index": ALL}, "command"),
    Input("bm-run", "n_clicks"),
    State("bm-model", "value"),
    State("bm-axis", "value"),
    State("bm-efforts", "value"),
    State("bm-budgets", "value"),
    State("bm-models", "value"),
    State("bm-fixed-budget", "value"),
    State("bm-fixed-effort", "value"),
    State("bm-prompt", "value"),
    prevent_initial_call=True,
)
def _run(
    _clicks, model, axis, efforts, budgets, models, fixed_budget, fixed_effort, prompt
):
    """START every variant, then return. The cells fill in as they draw.

    This used to block until all six calls had finished and then build the
    panels from their results, which meant a minute or more of spinner and —
    more to the point — no way to stop once the money was committed. Each
    variant is now a streamed run in the shared buffer, so the page can show
    six drawings appearing at once AND cancel them.
    """
    blank = [BLANK] * MAX_VARIANTS
    nothing = [no_update] * MAX_VARIANTS

    def refuse(message, color="yellow"):
        return None, True, message, color, blank, nothing, nothing

    if not prompt or not prompt.strip():
        return refuse("Write a prompt first.")

    # Same gate as /ai-agent, and it matters more here: one click is up to six
    # paid calls. See lib/scene_ai._spend_allowed.
    if not _spend_allowed():
        return refuse(
            "Sign in to run a benchmark — this page spends real API credits."
        )

    # Same builder the estimate uses, so the run cannot execute a different
    # matrix from the one that was priced above the button.
    variants = _variants(
        model, axis, efforts, budgets, models, fixed_budget, fixed_effort
    )
    if not variants:
        return refuse("Select at least one variant to compare.")

    if axis == "effort" and model not in EFFORT_CAPABLE:
        # Varying effort on a model that rejects the parameter would run N
        # identical calls and present them as a comparison — worse than an
        # error, because the output looks like a result.
        if len({e for _, e, _ in variants}) > 1:
            return refuse(
                f"{model} does not accept the effort parameter, so every variant "
                "would be identical. Switch to varying max tokens, or pick "
                "another model.",
                "red",
            )

    # The model axis has its own version of the same trap: one model selected
    # is not a comparison, it is a single call wearing a comparison's UI.
    if axis == "model" and len(variants) < 2:
        return refuse("Pick at least two models to compare — one is just a single run.")

    # Priced as a SWEEP, not per cell: six calls admitted one at a time would
    # each pass a check the six together fail, which is precisely the runaway
    # this page is most able to cause.
    try:
        spend.check(
            sum(
                estimate_cost(m, e, b)["typical"]
                for m, e, b in variants
            )
        )
    except spend.CeilingReached as exc:
        return refuse(str(exc))

    cells = []
    styles = list(blank)
    heads = list(nothing)
    commands = list(nothing)
    failed = []

    for index, (variant_model, effort, budget) in enumerate(variants):
        label = _variant_label(axis, variant_model, effort, budget)
        try:
            run_id = scene_stream.start(
                model=variant_model,
                user_prompt=prompt.strip(),
                max_tokens=budget,
                effort=effort,
            )
        except Exception as exc:  # noqa: BLE001 - one bad variant, not the sweep
            # A cell that cannot start must not take the others down with it;
            # that is the whole reason the sweep is worth running.
            failed.append(f"{label}: {type(exc).__name__}: {exc}")
            continue

        cell = {
            "id": run_id,
            "label": label,
            "model": variant_model,
            "cursor": 0,
            "done": False,
        }
        cells.append(cell)
        styles[index] = SHOWN
        heads[index] = _head(cell, {"all": [], "elapsed": 0.0, "done": False})
        # Blank the cell so the drawing starts from nothing rather than
        # appearing over the previous sweep's scene.
        commands[index] = {
            "id": f"bm-reset-{run_id[:8]}",
            "type": "resetScene",
            "payload": {},
        }

    if not cells:
        return refuse("No variant could be started. " + " · ".join(failed), "red")

    status = f"Running {len(cells)} variant{'s' if len(cells) != 1 else ''}…"
    if failed:
        status += f" ({len(failed)} could not start: {'; '.join(failed)})"
    return cells, False, status, "gray", styles, heads, commands


@callback(
    Output("bm-status", "children", allow_duplicate=True),
    Output("bm-status", "color", allow_duplicate=True),
    Output("bm-runs", "data", allow_duplicate=True),
    Output("bm-tick", "disabled", allow_duplicate=True),
    Output({"type": "bm-head", "index": ALL}, "children", allow_duplicate=True),
    Output({"type": "bm-canvas", "index": ALL}, "command", allow_duplicate=True),
    Input("bm-tick", "n_intervals"),
    State("bm-runs", "data"),
    prevent_initial_call=True,
)
def _tick(_n, cells):
    """Collect every cell's new elements in ONE poll.

    One ticker for the whole sweep rather than one per cell: six Intervals
    would be six callbacks a second contending for the same Store, and Dash
    gives no ordering guarantee between them.
    """
    nothing = [no_update] * MAX_VARIANTS
    if not cells:
        return no_update, no_update, no_update, True, nothing, nothing

    heads = list(nothing)
    commands = list(nothing)
    next_cells = []
    finished = 0
    total_cost = 0.0
    total_elements = 0
    slowest = 0.0

    for index, cell in enumerate(cells):
        state = scene_stream.take(cell["id"], cell.get("cursor", 0))
        if not state["found"]:
            # Expired, forgotten, or an instance restart took the store. Treat
            # it as finished rather than polling forever.
            next_cells.append({**cell, "done": True})
            finished += 1
            continue

        heads[index] = _head(cell, state)
        if state["elements"]:
            commands[index] = {
                "id": f"bm-{cell['id'][:8]}-{state['cursor']}",
                "type": "updateScene",
                "payload": {
                    "elements": state["all"],
                    # NEVER while drawing, or each poll is its own undo step.
                    "captureUpdate": "NEVER",
                    # These cells are 340px showing scenes laid out for
                    # 1200x800. Without refitting you watch a zoomed-in corner
                    # of a drawing rather than the drawing.
                    "scrollToContent": True,
                },
            }

        total_elements += len(state["all"])
        slowest = max(slowest, state["elapsed"])
        if state["done"]:
            finished += 1
            total_cost += _cell_cost(cell["model"], state.get("meta"))
            if not cell.get("done"):
                # Last poll for this cell: commit it as one undo step, then
                # drop it from the buffer.
                commands[index] = {
                    "id": f"bm-final-{cell['id'][:8]}",
                    "type": "updateScene",
                    "payload": {
                        "elements": state["all"],
                        "captureUpdate": "IMMEDIATELY",
                        "scrollToContent": True,
                    },
                }
                scene_stream.forget(cell["id"])
            next_cells.append({**cell, "cursor": state["cursor"], "done": True})
        else:
            next_cells.append({**cell, "cursor": state["cursor"]})

    all_done = finished == len(cells)
    if not all_done:
        status = (
            f"Drawing… {finished}/{len(cells)} variants finished · "
            f"{total_elements} elements so far ({slowest:.0f}s)"
        )
        return status, "gray", next_cells, False, heads, commands

    cancelled = sum(1 for c in cells if c.get("cancelled"))
    status = (
        f"{len(cells)} variant{'s' if len(cells) != 1 else ''} in {slowest:.0f}s "
        f"(wall clock — they ran together) · {total_elements} elements · "
        f"~${total_cost:.3f} total"
    )
    return status, "yellow" if cancelled else "green", next_cells, True, heads, commands


@callback(
    Output("bm-status", "children", allow_duplicate=True),
    Output("bm-status", "color", allow_duplicate=True),
    Output("bm-runs", "data", allow_duplicate=True),
    Output("bm-tick", "disabled", allow_duplicate=True),
    Input("bm-stop", "n_clicks"),
    State("bm-runs", "data"),
    prevent_initial_call=True,
)
def _stop(_clicks, cells):
    """Press the brakes on every variant at once.

    Six calls are six bills, so this cancels them all rather than asking which
    one. Each `cancel` closes that run's provider stream, so generation stops
    and billing stops at the tokens already produced — ending the poll alone
    would leave six models running to their full budgets unobserved.

    What is drawn stays drawn: a half-finished sweep is still a comparison,
    and it is usually the reason for stopping.
    """
    if not cells:
        return no_update, no_update, no_update, True

    stopped = sum(1 for cell in cells if scene_stream.cancel(cell["id"]))
    return (
        f"Stopped {stopped} variant{'s' if stopped != 1 else ''}. What was drawn "
        f"is kept; no further tokens are being generated.",
        "yellow",
        [{**cell, "cancelled": True} for cell in cells],
        True,
    )


@callback(
    Output("bm-run", "loading"),
    Output("bm-run", "disabled"),
    Output("bm-stop", "disabled"),
    Output("bm-prompt", "disabled"),
    Output("bm-axis", "disabled"),
    Input("bm-tick", "disabled"),
)
def _lock_controls(tick_disabled):
    """Keyed on the ticker, not on `_run`'s lifetime — that now returns in
    milliseconds, so a `running=` lock would release while six models were
    still drawing."""
    sweeping = not tick_disabled
    # Stop is enabled precisely when the rest are not.
    return sweeping, sweeping, not sweeping, sweeping, sweeping
