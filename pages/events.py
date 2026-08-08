"""Events: observe pointer/scroll/paste/library snapshots."""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback

from dash_excalidraw import DashExcalidraw
from pages._shared import (
    canvas_frame,
    code_block,
    json_panel,
    page_header,
    sync_canvas_theme,
    two_column,
)

sync_canvas_theme("events-canvas")

dash.register_page(
    __name__,
    path="/events",
    name="Events",
    description="Live-watch the last* event snapshot props",
    order=6,
)

CODE = """
@callback(
    Output('pointer-out', 'children'),
    Input('canvas', 'lastPointerMove'),
)
def show_pointer(snapshot):
    return json.dumps(snapshot) if snapshot else '(waiting)'
"""


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "Events",
            "Every Excalidraw callback is surfaced as a setProps-written "
            "snapshot prop on the Python side. Interact with the canvas and "
            "watch the panels update.",
        ),
        code_block(CODE),
        two_column(
            canvas_frame(
                DashExcalidraw(
                    id="events-canvas",
                    height="560px",
                    pointerMoveThrottleMs=75,
                    scrollThrottleMs=150,
                ),
                min_height=560,
            ),
            dmc.Stack(
                gap="sm",
                children=[
                    dmc.Tabs(
                        value="pointer",
                        children=[
                            dmc.TabsList(
                                [
                                    dmc.TabsTab("Pointer", value="pointer"),
                                    dmc.TabsTab("Scroll", value="scroll"),
                                    dmc.TabsTab("Paste", value="paste"),
                                    dmc.TabsTab("Links", value="links"),
                                ]
                            ),
                            dmc.TabsPanel(
                                value="pointer",
                                pt="sm",
                                children=dmc.Stack(
                                    gap="xs",
                                    children=[
                                        dmc.Text(
                                            "lastPointerDown / Up / Move",
                                            size="sm",
                                            fw=600,
                                        ),
                                        dmc.Paper(id="events-pointer", withBorder=True, p="xs"),
                                    ],
                                ),
                            ),
                            dmc.TabsPanel(
                                value="scroll",
                                pt="sm",
                                children=dmc.Paper(id="events-scroll", withBorder=True, p="xs"),
                            ),
                            dmc.TabsPanel(
                                value="paste",
                                pt="sm",
                                children=dmc.Paper(id="events-paste", withBorder=True, p="xs"),
                            ),
                            dmc.TabsPanel(
                                value="links",
                                pt="sm",
                                children=dmc.Paper(id="events-link", withBorder=True, p="xs"),
                            ),
                        ],
                    ),
                ],
            ),
        ),
    ],
)


@callback(
    Output("events-pointer", "children"),
    Input("events-canvas", "lastPointerDown"),
    Input("events-canvas", "lastPointerUp"),
    Input("events-canvas", "lastPointerMove"),
)
def _render_pointer(down, up, move):
    return dmc.Stack(
        gap="xs",
        children=[
            json_panel("lastPointerDown", down, height=120),
            json_panel("lastPointerUp", up, height=120),
            json_panel("lastPointerMove", move, height=120),
        ],
    )


@callback(
    Output("events-scroll", "children"),
    Input("events-canvas", "lastScrollChange"),
)
def _render_scroll(scroll):
    return json_panel("lastScrollChange", scroll, height=220)


@callback(
    Output("events-paste", "children"),
    Input("events-canvas", "lastPaste"),
)
def _render_paste(paste):
    return json_panel("lastPaste", paste, height=220)


@callback(
    Output("events-link", "children"),
    Input("events-canvas", "lastLinkOpen"),
)
def _render_link(link):
    return json_panel("lastLinkOpen", link, height=220)