"""UIOptions: toggle individual canvas actions and the welcome screen."""

import dash
import dash_mantine_components as dmc
from dash import Input, Output, callback

from dash_excalidraw import DashExcalidraw
from pages._shared import canvas_frame, code_block, page_header, sync_canvas_theme

sync_canvas_theme("ui-options-canvas")

dash.register_page(
    __name__,
    path="/ui-options",
    name="UIOptions",
    description="Canvas actions and welcome screen toggles",
    order=5,
)

CODE = """
DashExcalidraw(
    id='canvas',
    UIOptions={
        'welcomeScreen': False,
        'canvasActions': {
            'changeViewBackgroundColor': True,
            'clearCanvas': True,
            'export': True,
            'loadScene': True,
            'saveAsImage': True,
            'toggleTheme': True,
        },
        'tools': {'image': True},
    },
)
"""

ACTION_SWITCHES = [
    ("welcome", "welcomeScreen", "Welcome overlay on empty canvas"),
    ("clearCanvas", "canvasActions.clearCanvas", "Clear-canvas action in menu"),
    ("export", "canvasActions.export", "Export action in menu"),
    ("loadScene", "canvasActions.loadScene", "Load-scene action"),
    ("saveAsImage", "canvasActions.saveAsImage", "Save-as-image action"),
    ("toggleTheme", "canvasActions.toggleTheme", "Theme-toggle button"),
    ("changeBg", "canvasActions.changeViewBackgroundColor", "Bg color picker"),
    ("image", "tools.image", "Image tool"),
]


def _switch(key: str, label: str, desc: str, default: bool) -> dmc.Switch:
    return dmc.Switch(
        id=f"ui-{key}",
        label=label,
        description=desc,
        checked=default,
        size="sm",
    )


layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "UIOptions",
            "The JSON-safe subset of Excalidraw's UIOptions prop. Toggle the "
            "switches below and watch the canvas chrome change.",
        ),
        dmc.Alert(
            color="yellow",
            variant="light",
            title="welcomeScreen is mount-state, not reactive",
            children=(
                "Excalidraw only checks `welcomeScreen` while the canvas is "
                "still in its untouched initial state. Once the user draws "
                "or dismisses the overlay, toggling the switch can't bring "
                "it back — that's an upstream Excalidraw design decision. "
                "Reload the page to see the welcome screen again. The other "
                "switches are reactive and update the canvas chrome live."
            ),
        ),
        code_block(CODE),
        dmc.Paper(
            withBorder=True,
            p="md",
            radius="md",
            children=dmc.SimpleGrid(
                cols={"base": 1, "sm": 2, "md": 4},
                spacing="sm",
                children=[
                    _switch(key, label, desc, default=(key != "welcome"))
                    for key, label, desc in ACTION_SWITCHES
                ],
            ),
        ),
        canvas_frame(
            DashExcalidraw(
                id="ui-options-canvas",
                height="600px",
                UIOptions={
                    "welcomeScreen": False,
                    "canvasActions": {
                        "clearCanvas": True,
                        "export": True,
                        "loadScene": True,
                        "saveAsImage": True,
                        "toggleTheme": True,
                        "changeViewBackgroundColor": True,
                    },
                    "tools": {"image": True},
                },
            )
        ),
    ],
)


@callback(
    Output("ui-options-canvas", "UIOptions"),
    Input("ui-welcome", "checked"),
    Input("ui-clearCanvas", "checked"),
    Input("ui-export", "checked"),
    Input("ui-loadScene", "checked"),
    Input("ui-saveAsImage", "checked"),
    Input("ui-toggleTheme", "checked"),
    Input("ui-changeBg", "checked"),
    Input("ui-image", "checked"),
)
def _compose_ui_options(welcome, clear_, export, load, save_img, tog_theme, change_bg, image):
    return {
        "welcomeScreen": bool(welcome),
        "canvasActions": {
            "clearCanvas": bool(clear_),
            "export": bool(export),
            "loadScene": bool(load),
            "saveAsImage": bool(save_img),
            "toggleTheme": bool(tog_theme),
            "changeViewBackgroundColor": bool(change_bg),
        },
        "tools": {"image": bool(image)},
    }