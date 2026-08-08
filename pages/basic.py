"""Basic usage: the minimum viable DashExcalidraw."""

import dash
import dash_mantine_components as dmc

from dash_excalidraw import DashExcalidraw
from pages._shared import canvas_frame, code_block, page_header, sync_canvas_theme

sync_canvas_theme("basic-canvas")

dash.register_page(
    __name__,
    path="/basic",
    name="Basic usage",
    description="Bare DashExcalidraw with default props",
    order=1,
)

CODE = """
from dash import Dash
from dash_excalidraw import DashExcalidraw

app = Dash(__name__)
app.layout = DashExcalidraw(id='canvas', height='600px')
"""


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "Basic usage",
            "The smallest useful app — one component, default props. "
            "Draw on the canvas; zoom, pan, undo, library, and shape tools all "
            "just work.",
        ),
        code_block(CODE),
        canvas_frame(DashExcalidraw(id="basic-canvas", height="600px")),
    ],
)