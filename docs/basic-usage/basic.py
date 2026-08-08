"""Basic usage: the minimum viable DashExcalidraw."""

import dash_mantine_components as dmc

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame, code_block, sync_canvas_theme

sync_canvas_theme("basic-canvas")

CODE = """
from dash import Dash
from dash_excalidraw import DashExcalidraw

app = Dash(__name__)
app.layout = DashExcalidraw(id='canvas', height='600px')
"""


component = dmc.Stack(
    gap="md",
    children=[
        code_block(CODE),
        canvas_frame(DashExcalidraw(id="basic-canvas", height="600px")),
    ],
)