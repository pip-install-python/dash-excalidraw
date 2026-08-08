"""Command dispatch: drive Excalidraw imperatively from Python."""

from __future__ import annotations

import time
import uuid

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, no_update

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame, code_block, sync_canvas_theme

sync_canvas_theme("commands-canvas")

CODE = """
@callback(
    Output('canvas', 'command'),
    Input('btn-rect', 'n_clicks'),
    prevent_initial_call=True,
)
def pick_rectangle(_):
    return {
        'id': str(uuid.uuid4()),
        'type': 'setActiveTool',
        'payload': {'type': 'rectangle'},
    }
"""


def _btn(btn_id: str, label: str, color: str = "indigo") -> dmc.Button:
    return dmc.Button(label, id=btn_id, color=color, variant="light", size="sm")


component = dmc.Stack(
    gap="md",
    children=[
        code_block(CODE),
        dmc.Paper(
            withBorder=True,
            p="md",
            radius="md",
            children=dmc.Stack(
                gap="sm",
                children=[
                    dmc.Text("Scene", size="sm", fw=600, c="dimmed"),
                    dmc.Group(
                        [
                            _btn("cmd-update", "updateScene (seed)"),
                            _btn("cmd-reset", "resetScene", color="red"),
                            _btn("cmd-scrollto", "scrollToContent"),
                        ]
                    ),
                    dmc.Text("Tools", size="sm", fw=600, c="dimmed"),
                    dmc.Group(
                        [
                            _btn("cmd-tool-rect", "setActiveTool: rectangle"),
                            _btn("cmd-tool-arrow", "setActiveTool: arrow"),
                            _btn("cmd-tool-select", "setActiveTool: selection"),
                        ]
                    ),
                    dmc.Text("UI", size="sm", fw=600, c="dimmed"),
                    dmc.Group(
                        [
                            _btn("cmd-toast", "setToast"),
                            _btn("cmd-sidebar", "toggleSidebar"),
                        ]
                    ),
                ],
            ),
        ),
        canvas_frame(
            DashExcalidraw(
                id="commands-canvas",
                height="600px",
            )
        ),
    ],
)


def _cmd(type_: str, payload: dict | None = None) -> dict:
    return {"id": f"{type_}-{uuid.uuid4()}", "type": type_, "payload": payload or {}}


@callback(
    Output("commands-canvas", "command"),
    Input("cmd-update", "n_clicks"),
    Input("cmd-reset", "n_clicks"),
    Input("cmd-scrollto", "n_clicks"),
    Input("cmd-tool-rect", "n_clicks"),
    Input("cmd-tool-arrow", "n_clicks"),
    Input("cmd-tool-select", "n_clicks"),
    Input("cmd-toast", "n_clicks"),
    Input("cmd-sidebar", "n_clicks"),
    prevent_initial_call=True,
)
def _dispatch(update_, reset_, scrollto_, rect_, arrow_, sel_, toast_, sidebar_):
    trigger = dash.ctx.triggered_id
    if trigger == "cmd-update":
        return _cmd(
            "updateScene",
            {
                "elements": [
                    {
                        "id": f"seeded-{int(time.time())}",
                        "type": "ellipse",
                        "x": 200,
                        "y": 200,
                        "width": 300,
                        "height": 180,
                        "angle": 0,
                        "strokeColor": "#e67700",
                        "backgroundColor": "#fff4e6",
                        "fillStyle": "solid",
                        "strokeWidth": 2,
                        "roughness": 1,
                        "opacity": 100,
                        "seed": 42,
                        "version": 1,
                        "versionNonce": 42,
                        "isDeleted": False,
                        "groupIds": [],
                        "frameId": None,
                        "boundElements": [],
                        "updated": 1,
                        "link": None,
                        "locked": False,
                    }
                ]
            },
        )
    if trigger == "cmd-reset":
        return _cmd("resetScene")
    if trigger == "cmd-scrollto":
        return _cmd("scrollToContent", {"opts": {"fitToViewport": True}})
    if trigger == "cmd-tool-rect":
        return _cmd("setActiveTool", {"type": "rectangle"})
    if trigger == "cmd-tool-arrow":
        return _cmd("setActiveTool", {"type": "arrow"})
    if trigger == "cmd-tool-select":
        return _cmd("setActiveTool", {"type": "selection"})
    if trigger == "cmd-toast":
        return _cmd(
            "setToast",
            {"message": "Toast dispatched from Python!", "duration": 2500},
        )
    if trigger == "cmd-sidebar":
        return _cmd("toggleSidebar", {"name": "library"})
    return no_update