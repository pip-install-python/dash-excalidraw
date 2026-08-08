"""Library: observe library items and drive updateLibrary."""

import uuid

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

sync_canvas_theme("library-canvas")

dash.register_page(
    __name__,
    path="/library",
    name="Library",
    description="Library items: observe and dispatch updates",
    order=10,
)

CODE = """
# observe
@callback(Output('out', 'children'),
          Input('canvas', 'lastLibraryChange'))
def show(snapshot): ...

# drive (merge items from Python)
@callback(Output('canvas', 'command'),
          Input('btn', 'n_clicks'),
          prevent_initial_call=True)
def add_items(_):
    return {'id': str(uuid.uuid4()),
            'type': 'updateLibrary',
            'payload': {
                'libraryItems': [...],
                'merge': True,
                'openLibraryMenu': True,
            }}
"""


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "Library",
            "The library menu holds reusable shapes. `lastLibraryChange` fires "
            "whenever the user adds/removes an item; `command: updateLibrary` "
            "lets you push items in from Python.",
        ),
        code_block(CODE),
        two_column(
            canvas_frame(
                DashExcalidraw(
                    id="library-canvas",
                    height="560px",
                ),
                min_height=560,
            ),
            dmc.Stack(
                gap="sm",
                children=[
                    dmc.Button(
                        "Open library menu",
                        id="library-open-btn",
                        variant="light",
                    ),
                    dmc.Paper(id="library-panel", withBorder=True, p="xs"),
                ],
            ),
        ),
    ],
)


@callback(
    Output("library-panel", "children"),
    Input("library-canvas", "lastLibraryChange"),
)
def _render_library(snapshot):
    if not snapshot:
        return dmc.Text("(no library changes yet)", c="dimmed", size="sm")
    items = snapshot.get("items") or []
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Group(
                [
                    dmc.Text("Library items", size="sm", fw=600),
                    dmc.Badge(len(items), variant="light"),
                ]
            ),
            json_panel("Raw payload", snapshot, height=320),
        ],
    )


@callback(
    Output("library-canvas", "command"),
    Input("library-open-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _open_library(_clicks):
    return {
        "id": f"libopen-{uuid.uuid4()}",
        "type": "toggleSidebar",
        "payload": {"name": "library", "force": True},
    }