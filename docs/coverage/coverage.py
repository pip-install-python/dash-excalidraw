"""Coverage: the three commands and ten props no other example page reaches.

Measured, not guessed — an AST sweep of every `docs/*/*.py` for command types
(both the `{"type": "X"}` dict literal and the `_cmd("X", ...)` helper form)
and for props reached via a constructor kwarg or an Input/Output/State
dependency. What was left over is what this page exists to exercise.
"""

import time
import uuid

import dash_mantine_components as dmc
from dash import Input, Output, State, callback, html, no_update

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame, code_block, json_panel, sync_canvas_theme, two_column

sync_canvas_theme("coverage-canvas")

# A real 1x1 PNG. Small enough to read inline, valid enough that Excalidraw
# accepts it as BinaryFileData rather than silently dropping the entry.
PNG_1PX = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

CODE = """
# The three commands no other page dispatches.

# addFiles — RAW BinaryFileData list. You supply `created` and `mimeType`;
# an entry missing either is ignored, so a bad payload is a silent no-op.
{'id': cmd_id, 'type': 'addFiles',
 'payload': [{'id': file_id, 'mimeType': 'image/png',
              'dataURL': PNG_1PX, 'created': int(time.time() * 1000)}]}

# exportToCanvas — async; the result arrives on `lastExport`, carrying the
# id you dispatched. A data: URL, not an SVG string.
{'id': cmd_id, 'type': 'exportToCanvas', 'payload': {'mimeType': 'image/png'}}

# updateLibrary — merge items into the user's library.
{'id': cmd_id, 'type': 'updateLibrary',
 'payload': {'libraryItems': [item], 'merge': True, 'openLibraryMenu': True}}
"""


def _rect(x: int, y: int, colour: str, bg: str) -> dict:
    now = int(time.time())
    return {
        "id": f"cov-{uuid.uuid4()}",
        "type": "rectangle",
        "x": x,
        "y": y,
        "width": 120,
        "height": 80,
        "angle": 0,
        "strokeColor": colour,
        "backgroundColor": bg,
        "fillStyle": "solid",
        "strokeWidth": 2,
        "roughness": 1,
        "opacity": 100,
        "seed": now % 100000,
        "version": 1,
        "versionNonce": now % 100000,
        "isDeleted": False,
        "groupIds": [],
        "frameId": None,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    }


def _btn(btn_id: str, label: str, colour: str) -> dmc.Button:
    return dmc.Button(label, id=btn_id, color=colour, size="sm", variant="light")


LANGS = ["en", "fr-FR", "de-DE", "zh-CN", "es-ES"]

controls = dmc.Paper(
    withBorder=True,
    p="md",
    radius="md",
    children=dmc.Stack(
        gap="sm",
        children=[
            dmc.Text("Props no other page sets", size="sm", fw=600, c="dimmed"),
            dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "md": 3},
                spacing="sm",
                children=[
                    dmc.Select(
                        id="cov-lang",
                        label="langCode",
                        description="Excalidraw UI language",
                        data=LANGS,
                        value="en",
                        size="xs",
                    ),
                    dmc.Select(
                        id="cov-name",
                        label="name",
                        description="Scene name in the export dialog",
                        data=["coverage-scene", "renamed-scene"],
                        value="coverage-scene",
                        size="xs",
                    ),
                    dmc.Select(
                        id="cov-width",
                        label="width",
                        description="CSS width of the container",
                        data=["100%", "75%", "50%"],
                        value="100%",
                        size="xs",
                    ),
                    dmc.Switch(
                        id="cov-detectscroll",
                        label="detectScroll",
                        description="Canvas handles wheel events",
                        checked=True,
                        size="sm",
                    ),
                    dmc.Switch(
                        id="cov-keyboard",
                        label="handleKeyboardGlobally",
                        description="Key handling on document, not canvas",
                        checked=True,
                        size="sm",
                    ),
                    dmc.Switch(
                        id="cov-hidelinks",
                        label="hideExcalidrawLinks",
                        description="Hides the GitHub/Discord/X menu group",
                        checked=True,
                        size="sm",
                    ),
                ],
            ),
        ],
    ),
)

component = dmc.Stack(
    gap="md",
    children=[
        dmc.Alert(
            color="blue",
            variant="light",
            title="What this page is for",
            children=(
                "Every other example page demonstrates a feature. This one "
                "exists to cover the leftovers: the three command types and "
                "ten props that no other page reaches. If a prop is listed "
                "in the component reference but you cannot find it exercised "
                "anywhere, it is here."
            ),
        ),
        code_block(CODE),
        dmc.Group(
            gap="sm",
            children=[
                _btn("cov-addfiles", "addFiles", "grape"),
                _btn("cov-exportcanvas", "exportToCanvas", "teal"),
                _btn("cov-updatelibrary", "updateLibrary", "indigo"),
            ],
        ),
        controls,
        two_column(
            canvas_frame(
                DashExcalidraw(
                    id="coverage-canvas",
                    height="520px",
                    width="100%",
                    name="coverage-scene",
                    langCode="en",
                    detectScroll=True,
                    handleKeyboardGlobally=True,
                    hideExcalidrawLinks=True,
                    # autoFocus is read by Excalidraw at MOUNT only, so a
                    # switch for it would be theatre — it is set here and
                    # takes effect on page load, nowhere else.
                    autoFocus=False,
                    # Only observable by taking the Browse Library round trip;
                    # it is where that trip returns to.
                    libraryReturnUrl="https://excalidraw.2plot.dev/coverage",
                )
            ),
            dmc.Stack(
                gap="sm",
                children=[
                    html.Div(id="cov-readout"),
                    html.Div(id="cov-export-out"),
                ],
            ),
        ),
    ],
)


@callback(
    Output("coverage-canvas", "langCode"),
    Output("coverage-canvas", "name"),
    Output("coverage-canvas", "width"),
    Output("coverage-canvas", "detectScroll"),
    Output("coverage-canvas", "handleKeyboardGlobally"),
    Output("coverage-canvas", "hideExcalidrawLinks"),
    Input("cov-lang", "value"),
    Input("cov-name", "value"),
    Input("cov-width", "value"),
    Input("cov-detectscroll", "checked"),
    Input("cov-keyboard", "checked"),
    Input("cov-hidelinks", "checked"),
)
def _drive_props(lang, name, width, detect, keyboard, hidelinks):
    return lang, name, width, bool(detect), bool(keyboard), bool(hidelinks)


@callback(
    Output("coverage-canvas", "command"),
    Input("cov-addfiles", "n_clicks"),
    Input("cov-exportcanvas", "n_clicks"),
    Input("cov-updatelibrary", "n_clicks"),
    prevent_initial_call=True,
)
def _dispatch(_add, _export, _library):
    import dash

    trigger = dash.ctx.triggered_id
    cmd_id = str(uuid.uuid4())

    if trigger == "cov-addfiles":
        return {
            "id": cmd_id,
            "type": "addFiles",
            "payload": [
                {
                    "id": f"cov-file-{cmd_id[:8]}",
                    "mimeType": "image/png",
                    "dataURL": PNG_1PX,
                    "created": int(time.time() * 1000),
                }
            ],
        }

    if trigger == "cov-exportcanvas":
        return {
            "id": cmd_id,
            "type": "exportToCanvas",
            "payload": {"mimeType": "image/png"},
        }

    if trigger == "cov-updatelibrary":
        return {
            "id": cmd_id,
            "type": "updateLibrary",
            "payload": {
                "libraryItems": [
                    {
                        "id": f"cov-lib-{cmd_id[:8]}",
                        "status": "unpublished",
                        "created": int(time.time() * 1000),
                        "elements": [
                            _rect(100, 100, "#5f3dc4", "#d0bfff"),
                            _rect(240, 100, "#0b7285", "#99e9f2"),
                        ],
                    }
                ],
                "merge": True,
                "openLibraryMenu": True,
            },
        }

    return no_update


@callback(
    Output("cov-readout", "children"),
    Input("coverage-canvas", "sceneVersion"),
    State("coverage-canvas", "appState"),
    State("coverage-canvas", "files"),
)
def _readout(scene_version, app_state, files):
    state = app_state or {}
    return json_panel(
        "sceneVersion + appState (both read-only)",
        {
            "sceneVersion": scene_version,
            "registered file ids": sorted((files or {}).keys()),
            "appState.zoom": (state.get("zoom") or {}).get("value"),
            "appState.scrollX": state.get("scrollX"),
            "appState.scrollY": state.get("scrollY"),
            "appState.viewBackgroundColor": state.get("viewBackgroundColor"),
            "appState.activeTool": (state.get("activeTool") or {}).get("type"),
        },
        height=200,
    )


@callback(
    Output("cov-export-out", "children"),
    Input("coverage-canvas", "lastExport"),
    prevent_initial_call=True,
)
def _show_export(export):
    if not export:
        return no_update
    if export.get("error"):
        return dmc.Alert(
            f"{export['type']} (id {export['id']}) failed: {export['error']}",
            color="red",
            variant="light",
        )
    result = export.get("result") or ""
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Text(
                f"lastExport carries id {export.get('id')} for {export.get('type')}",
                size="sm",
                fw=600,
            ),
            dmc.Image(src=result, h=120, fit="contain")
            if result.startswith("data:image")
            else dmc.Code(result[:200], block=True),
        ],
    )
