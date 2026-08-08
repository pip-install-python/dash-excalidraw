"""Collaboration: isCollaborating + appState.collaborators scaffolding."""

import uuid

import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback

from dash_excalidraw import DashExcalidraw
from pages._shared import canvas_frame, code_block, page_header, sync_canvas_theme

sync_canvas_theme("collaboration-canvas")

dash.register_page(
    __name__,
    path="/collaboration",
    name="Collaboration",
    description="isCollaborating + collaborator pointer rendering",
    order=11,
)

CODE = """
DashExcalidraw(
    id='canvas',
    isCollaborating=True,
)

# Feed collaborators via an updateScene command:
{'id': ..., 'type': 'updateScene',
 'payload': {
     'collaborators': {
         'user-1': {
             'username': 'Alice',
             'color': {'background': '#ff6b6b', 'stroke': '#c92a2a'},
             'pointer': {'x': 300, 'y': 240, 'tool': 'laser'},
         },
     },
 }}
"""


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "Collaboration",
            "The wrapper does not ship a transport layer, but it exposes the "
            "knobs: `isCollaborating` toggles the collaborator UI, and "
            "`appState.collaborators` can be driven via the updateScene command.",
        ),
        dmc.Alert(
            color="blue",
            variant="light",
            children="This example only simulates a single fake cursor from a timer — "
            "hook it up to a real backend (Socket.IO, Firestore, Liveblocks, ...) "
            "to make it collaborative.",
        ),
        code_block(CODE),
        dmc.Group(
            [
                dmc.Switch(
                    id="collab-switch",
                    checked=True,
                    label="isCollaborating",
                    size="md",
                ),
                dmc.Button(
                    "Simulate Alice's cursor",
                    id="collab-simulate-btn",
                    variant="light",
                ),
            ]
        ),
        canvas_frame(
            DashExcalidraw(
                id="collaboration-canvas",
                height="560px",
                isCollaborating=True,
            )
        ),
    ],
)


@callback(
    Output("collaboration-canvas", "isCollaborating"),
    Input("collab-switch", "checked"),
)
def _toggle(checked):
    return bool(checked)


@callback(
    Output("collaboration-canvas", "command"),
    Input("collab-simulate-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _simulate(n):
    x = 200 + (n or 0) * 40
    return {
        "id": f"collab-{uuid.uuid4()}",
        "type": "updateScene",
        "payload": {
            "appState": {
                "collaborators": {
                    "user-alice": {
                        "username": "Alice",
                        "color": {
                            "background": "#ff6b6b",
                            "stroke": "#c92a2a",
                        },
                        "pointer": {"x": x, "y": 260, "tool": "laser"},
                    }
                }
            }
        },
    }