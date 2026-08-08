"""initialData: seed the scene on mount."""

import dash_mantine_components as dmc

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame, code_block, sync_canvas_theme

sync_canvas_theme("initialdata-canvas")

SEED_ELEMENTS = [
    {
        "id": "rect-1",
        "type": "rectangle",
        "x": 120,
        "y": 120,
        "width": 260,
        "height": 140,
        "angle": 0,
        "strokeColor": "#1971c2",
        "backgroundColor": "#d0ebff",
        "fillStyle": "solid",
        "strokeWidth": 2,
        "roughness": 1,
        "opacity": 100,
        "seed": 1,
        "version": 1,
        "versionNonce": 1,
        "isDeleted": False,
        "groupIds": [],
        "frameId": None,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
    },
    {
        "id": "text-1",
        "type": "text",
        "x": 150,
        "y": 170,
        "width": 210,
        "height": 40,
        "angle": 0,
        "strokeColor": "#1864ab",
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "roughness": 0,
        "opacity": 100,
        "seed": 2,
        "version": 1,
        "versionNonce": 2,
        "isDeleted": False,
        "groupIds": [],
        "frameId": None,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
        "fontSize": 28,
        "fontFamily": 1,
        "text": "Hello from Dash!",
        "textAlign": "center",
        "verticalAlign": "middle",
        "containerId": None,
        "originalText": "Hello from Dash!",
        "lineHeight": 1.25,
    },
]

INITIAL_DATA = {
    "elements": SEED_ELEMENTS,
    "appState": {
        "viewBackgroundColor": "#f8f9fa",
        "gridSize": None,
    },
    "scrollToContent": True,
}

CODE = """
SEED = {
    'elements': [
        {'type': 'rectangle', 'x': 120, 'y': 120,
         'width': 260, 'height': 140, ...},
        {'type': 'text', 'x': 150, 'y': 170,
         'text': 'Hello from Dash!', ...},
    ],
    'appState': {'viewBackgroundColor': '#f8f9fa'},
    'scrollToContent': True,
}

DashExcalidraw(id='canvas', initialData=SEED)
"""


component = dmc.Stack(
    gap="md",
    children=[
        code_block(CODE),
        dmc.Alert(
            color="yellow",
            variant="light",
            title="Why not just update this prop later?",
            children="Excalidraw owns the scene state after mount. Overwriting "
            "initialData after render would fight the editor's internal state and "
            "history stack. Use `command` with type='updateScene' or 'resetScene' "
            "for post-mount changes.",
        ),
        canvas_frame(
            DashExcalidraw(
                id="initialdata-canvas",
                height="600px",
                initialData=INITIAL_DATA,
            )
        ),
    ],
)