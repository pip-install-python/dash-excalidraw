"""Helpers shared across example pages."""

from __future__ import annotations

import json
from typing import Any

import dash_mantine_components as dmc
from dash import Input, Output, clientside_callback


def sync_canvas_theme(canvas_id: str) -> None:
    """Tie a `DashExcalidraw(id=canvas_id)` to the app shell's color scheme.

    Every page except `/theming` (which demos the prop directly) calls this
    at module load so the canvas re-themes the instant the user flips the
    global light / dark switch in the header. Runs clientside so there's no
    Dash callback round-trip.

    The input is `color-scheme-storage`, the boilerplate AppShell's store
    (components/appshell.py). It was `color-scheme-store`, an id defined by
    this project's own app.py — deleting that file without rewiring here
    would raise a nonexistent-input error on EVERY page at once.
    """
    clientside_callback(
        "function(scheme) { return scheme || 'light'; }",
        Output(canvas_id, "theme"),
        Input("color-scheme-storage", "data"),
    )


def page_header(title: str, subtitle: str) -> dmc.Stack:
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Title(title, order=2),
            dmc.Text(subtitle, c="dimmed", size="sm"),
            dmc.Divider(my="sm"),
        ],
    )


def code_block(source: str, language: str = "python") -> dmc.CodeHighlight:
    return dmc.CodeHighlight(
        code=source.strip("\n"),
        language=language,
        withCopyButton=True,
    )


def canvas_frame(component, min_height: int = 500) -> dmc.Paper:
    """Wrap the canvas in a Paper so it sits cleanly in the app shell."""
    return dmc.Paper(
        component,
        withBorder=True,
        radius="md",
        shadow="sm",
        style={"overflow": "hidden", "minHeight": f"{min_height}px"},
    )


def json_panel(title: str, payload: Any, height: int = 220) -> dmc.Paper:
    """Render a JSON snapshot of a prop/state object."""
    try:
        rendered = json.dumps(payload, indent=2, default=str)
    except (TypeError, ValueError):
        rendered = str(payload)
    return dmc.Paper(
        withBorder=True,
        p="sm",
        radius="md",
        children=dmc.Stack(
            gap="xs",
            children=[
                dmc.Text(title, size="sm", fw=600, c="dimmed"),
                dmc.ScrollArea(
                    style={"height": height},
                    children=dmc.Code(
                        rendered,
                        block=True,
                        style={"whiteSpace": "pre-wrap", "wordBreak": "break-word"},
                    ),
                ),
            ],
        ),
    )


def two_column(left, right, left_span: int = 7, right_span: int = 5) -> dmc.Grid:
    return dmc.Grid(
        gutter="md",
        children=[
            dmc.GridCol(left, span={"base": 12, "md": left_span}),
            dmc.GridCol(right, span={"base": 12, "md": right_span}),
        ],
    )