"""Export: drive exportToSvg / exportToBlob / exportToCanvas via command."""

import uuid

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, html, no_update

from dash_excalidraw import DashExcalidraw
from pages._shared import (
    canvas_frame,
    code_block,
    page_header,
    sync_canvas_theme,
    two_column,
)

sync_canvas_theme("export-canvas")

dash.register_page(
    __name__,
    path="/export",
    name="Export",
    description="SVG / PNG export via the command round-trip",
    order=8,
)

CODE = """
# Python -> component: dispatch an export command
return {'id': str(uuid.uuid4()),
        'type': 'exportToSvg',
        'payload': {'exportPadding': 20}}

# component -> Python: observe lastExport and match ids
@callback(Output('preview', 'children'),
          Input('canvas', 'lastExport'))
def preview(result):
    if result and result['type'] == 'exportToSvg':
        return html.Iframe(srcDoc=result['result'])
"""


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "Export round-trip",
            "Excalidraw's export utilities are async. The wrapper models the "
            "round-trip as (1) Python writes `command`, (2) JS awaits the "
            "export and writes `lastExport` with the same id, (3) Python "
            "reads the result.",
        ),
        code_block(CODE),
        two_column(
            canvas_frame(
                DashExcalidraw(
                    id="export-canvas",
                    height="520px",
                    initialData={
                        "elements": [
                            {
                                "id": "s1",
                                "type": "rectangle",
                                "x": 150,
                                "y": 150,
                                "width": 220,
                                "height": 140,
                                "angle": 0,
                                "strokeColor": "#2f9e44",
                                "backgroundColor": "#d3f9d8",
                                "fillStyle": "solid",
                                "strokeWidth": 2,
                                "roughness": 1,
                                "opacity": 100,
                                "seed": 7,
                                "version": 1,
                                "versionNonce": 7,
                                "isDeleted": False,
                                "groupIds": [],
                                "frameId": None,
                                "boundElements": [],
                                "updated": 1,
                                "link": None,
                                "locked": False,
                            }
                        ],
                        "scrollToContent": True,
                    },
                ),
                min_height=520,
            ),
            dmc.Stack(
                gap="sm",
                children=[
                    dmc.Paper(
                        withBorder=True,
                        p="md",
                        radius="md",
                        children=dmc.Stack(
                            gap="sm",
                            children=[
                                dmc.Text("Dispatch", size="sm", fw=600, c="dimmed"),
                                dmc.Group(
                                    [
                                        dmc.Button(
                                            "Export SVG",
                                            id="export-svg-btn",
                                            variant="light",
                                        ),
                                        dmc.Button(
                                            "Export PNG",
                                            id="export-png-btn",
                                            variant="light",
                                            color="teal",
                                        ),
                                    ]
                                ),
                            ],
                        ),
                    ),
                    dmc.Paper(
                        withBorder=True,
                        p="md",
                        radius="md",
                        children=dmc.Stack(
                            gap="sm",
                            children=[
                                dmc.Text("Preview", size="sm", fw=600, c="dimmed"),
                                dmc.Box(id="export-preview", style={"minHeight": 180}),
                            ],
                        ),
                    ),
                ],
            ),
        ),
    ],
)


@callback(
    Output("export-canvas", "command"),
    Input("export-svg-btn", "n_clicks"),
    Input("export-png-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _dispatch_export(_svg, _png):
    trigger = dash.ctx.triggered_id
    if trigger == "export-svg-btn":
        return {
            "id": f"svg-{uuid.uuid4()}",
            "type": "exportToSvg",
            "payload": {"exportPadding": 20},
        }
    if trigger == "export-png-btn":
        return {
            "id": f"png-{uuid.uuid4()}",
            "type": "exportToBlob",
            "payload": {"mimeType": "image/png", "exportPadding": 20},
        }
    return no_update


@callback(
    Output("export-preview", "children"),
    Input("export-canvas", "lastExport"),
)
def _render_preview(result):
    if not result or "result" not in result:
        return dmc.Text("(dispatch an export to preview)", c="dimmed", size="sm")
    export_type = result.get("type")
    payload = result.get("result")
    if not payload:
        err = result.get("error") or "empty result"
        return dmc.Alert(color="red", variant="light", children=str(err))
    if export_type == "exportToSvg":
        return html.Iframe(
            srcDoc=payload,
            style={
                "width": "100%",
                "height": "260px",
                "border": "0",
                "background": "white",
            },
        )
    if export_type in ("exportToBlob", "exportToCanvas"):
        return html.Img(
            src=payload,
            style={"maxWidth": "100%", "maxHeight": "260px", "display": "block"},
        )
    return dmc.Text(f"Unhandled export type: {export_type}", c="dimmed")