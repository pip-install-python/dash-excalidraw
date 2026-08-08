"""Persistence: save to dcc.Store and restore on reload."""

import json
import uuid

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, dcc, no_update

from dash_excalidraw import DashExcalidraw
from pages._shared import canvas_frame, code_block, page_header, sync_canvas_theme

sync_canvas_theme("persistence-canvas")

dash.register_page(
    __name__,
    path="/persistence",
    name="Persistence",
    description="Save / restore via dcc.Store and serializedData",
    order=9,
)

CODE = """
# 1. observe serializedData
@callback(Output('store', 'data'),
          Input('canvas', 'serializedData'),
          prevent_initial_call=True)
def save(snapshot):
    return snapshot

# 2. on reload, hand the stored snapshot back as a command
@callback(Output('canvas', 'command'),
          Input('btn-restore', 'n_clicks'),
          State('store', 'data'),
          prevent_initial_call=True)
def restore(_, snapshot):
    data = json.loads(snapshot)
    return {'id': str(uuid.uuid4()),
            'type': 'updateScene',
            'payload': {'elements': data['elements'],
                        'appState': data.get('appState', {})}}
"""


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "Persistence",
            "`serializedData` gives you the canonical Excalidraw envelope on "
            "every change — stream it to a dcc.Store, write it back to a DB, "
            "restore it via `command` with type='updateScene'.",
        ),
        code_block(CODE),
        dcc.Store(id="persistence-store", storage_type="session"),
        dmc.Group(
            [
                dmc.Badge(
                    id="persistence-indicator",
                    children="Waiting for changes",
                    color="gray",
                    variant="light",
                ),
                dmc.Button(
                    "Restore from store",
                    id="persistence-restore-btn",
                    variant="light",
                    color="teal",
                ),
                dmc.Button(
                    "Clear store",
                    id="persistence-clear-btn",
                    variant="subtle",
                    color="red",
                ),
            ],
            justify="flex-start",
        ),
        canvas_frame(
            DashExcalidraw(
                id="persistence-canvas",
                height="600px",
            )
        ),
    ],
)


@callback(
    Output("persistence-store", "data"),
    Output("persistence-indicator", "children"),
    Output("persistence-indicator", "color"),
    Input("persistence-canvas", "serializedData"),
    Input("persistence-clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _save(serialized, _clear_clicks):
    trigger = dash.ctx.triggered_id
    if trigger == "persistence-clear-btn":
        return None, "Cleared", "red"
    if not serialized:
        return no_update, "No data yet", "gray"
    # Excalidraw fires onChange once on mount with an empty scene.
    # Without this guard, that first emit would clobber whatever the
    # store had from a previous session the moment the page loaded —
    # then clicking Restore would hand back an empty canvas.
    try:
        parsed = json.loads(serialized)
    except (TypeError, ValueError):
        return no_update, "Invalid snapshot", "yellow"
    if not parsed.get("elements"):
        return no_update, "Waiting for content…", "gray"
    return serialized, "Saved", "green"


@callback(
    Output("persistence-canvas", "command"),
    Input("persistence-restore-btn", "n_clicks"),
    State("persistence-store", "data"),
    prevent_initial_call=True,
)
def _restore(_clicks, snapshot):
    if not snapshot:
        return no_update
    try:
        parsed = json.loads(snapshot)
    except (TypeError, ValueError):
        return no_update
    return {
        "id": f"restore-{uuid.uuid4()}",
        "type": "updateScene",
        "payload": {
            "elements": parsed.get("elements", []),
            "appState": parsed.get("appState", {}),
        },
    }