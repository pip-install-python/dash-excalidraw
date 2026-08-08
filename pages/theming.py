"""Theming: light/dark mode wired to a segmented control."""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback

from dash_excalidraw import DashExcalidraw
from pages._shared import canvas_frame, code_block, page_header

dash.register_page(
    __name__,
    path="/theming",
    name="Theming",
    description="Light/dark theme and view background color",
    order=3,
)

CODE = """
from dash import Input, Output, callback

@callback(
    Output('canvas', 'theme'),
    Input('theme-picker', 'value'),
)
def set_theme(theme):
    return theme
"""


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "Theming",
            "Set `theme='light'` or `'dark'` — Excalidraw repaints the canvas, "
            "toolbar, and library accordingly. Pair with dmc.MantineProvider "
            "color-scheme for a consistent look.",
        ),
        code_block(CODE),
        dmc.Group(
            justify="flex-start",
            children=[
                dmc.SegmentedControl(
                    id="theme-picker",
                    value="light",
                    data=[
                        {"label": "Light", "value": "light"},
                        {"label": "Dark", "value": "dark"},
                    ],
                ),
            ],
        ),
        canvas_frame(
            DashExcalidraw(
                id="theming-canvas",
                height="600px",
                theme="light",
            )
        ),
    ],
)


@callback(
    Output("theming-canvas", "theme"),
    Input("theme-picker", "value"),
)
def _set_theme(value):
    return value or "light"