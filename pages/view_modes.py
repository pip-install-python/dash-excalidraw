"""View modes: view/zen/grid toggles driven from Python."""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback

from dash_excalidraw import DashExcalidraw
from pages._shared import canvas_frame, code_block, page_header, sync_canvas_theme

sync_canvas_theme("viewmodes-canvas")

dash.register_page(
    __name__,
    path="/view-modes",
    name="View modes",
    description="viewModeEnabled, zenModeEnabled, gridModeEnabled",
    order=4,
)

CODE = """
DashExcalidraw(
    id='canvas',
    viewModeEnabled=False,   # hides drawing tools when True
    zenModeEnabled=False,    # hides most chrome
    gridModeEnabled=False,   # grid + snap
)
"""


def _mode_switch(switch_id: str, label: str, description: str) -> dmc.Switch:
    return dmc.Switch(
        id=switch_id,
        label=label,
        description=description,
        checked=False,
        size="md",
    )


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "View modes",
            "Three boolean props flip the editor's mode. They are purely "
            "declarative — set them from any callback.",
        ),
        code_block(CODE),
        dmc.Group(
            children=[
                _mode_switch(
                    "view-mode-switch",
                    "viewModeEnabled",
                    "Disables drawing; pan & zoom remain.",
                ),
                _mode_switch(
                    "zen-mode-switch",
                    "zenModeEnabled",
                    "Hides library, menus, and footer.",
                ),
                _mode_switch(
                    "grid-mode-switch",
                    "gridModeEnabled",
                    "Snap-to-grid with a visible grid.",
                ),
            ],
        ),
        canvas_frame(
            DashExcalidraw(
                id="viewmodes-canvas",
                height="600px",
            )
        ),
    ],
)


@callback(
    Output("viewmodes-canvas", "viewModeEnabled"),
    Output("viewmodes-canvas", "zenModeEnabled"),
    Output("viewmodes-canvas", "gridModeEnabled"),
    Input("view-mode-switch", "checked"),
    Input("zen-mode-switch", "checked"),
    Input("grid-mode-switch", "checked"),
)
def _apply_modes(view, zen, grid):
    return bool(view), bool(zen), bool(grid)