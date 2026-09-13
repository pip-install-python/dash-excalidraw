"""UIOptions: toggle individual canvas actions and the welcome screen."""

import dash_mantine_components as dmc
from dash import Input, Output, callback

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame, code_block, sync_canvas_theme

sync_canvas_theme("ui-options-canvas")
sync_canvas_theme("ui-links-vendor-canvas")
sync_canvas_theme("ui-links-none-canvas")

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


component = dmc.Stack(
    gap="md",
    children=[
        dmc.Alert(
            color="blue",
            variant="light",
            title="welcomeScreen is a prop now, and it is reactive",
            children=(
                "`UIOptions.welcomeScreen` is read once while the canvas "
                "mounts, so a switch bound to it does nothing after the first "
                "paint. The overlay's real home is `appState.showWelcomeScreen`, "
                "so the component takes a top-level `welcomeScreen` prop and "
                "pushes it there — the switch below brings the overlay back "
                "after you have drawn on the canvas and dismissed it. "
                "`welcomeScreenContent={'title': …, 'subtitle': …}` puts your "
                "own words on it."
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
                # The overlay is driven by the top-level `welcomeScreen`
                # prop below, not by this key — see the note above.
                welcomeScreen=False,
                welcomeScreenContent={
                    "title": "dash-excalidraw",
                    "subtitle": "Draw something, or load a scene from Python.",
                },
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
        dmc.Divider(
            my="lg",
            label="The other two link states — open the hamburger menu on each",
            labelPosition="center",
        ),
        # STACKED, not side by side. The point of these two is that you open
        # the hamburger menu on each, and that menu is ~300px wide with a tall
        # item list. Two of them in a column that is itself only ~860px left
        # each canvas around 420px, so the menu covered most of its own canvas
        # and the two examples read as broken rather than as different. A
        # comparison you cannot see is not a comparison.
        dmc.SimpleGrid(
            cols=1,
            spacing="md",
            children=[
                dmc.Stack(
                    gap="xs",
                    children=[
                        dmc.Text(
                            "hideExcalidrawLinks=False — both groups",
                            size="sm",
                            fw=600,
                        ),
                        canvas_frame(
                            DashExcalidraw(
                                id="ui-links-vendor-canvas",
                                height="360px",
                                hideExcalidrawLinks=False,
                            ),
                            min_height=360,
                        ),
                    ],
                ),
                dmc.Stack(
                    gap="xs",
                    children=[
                        dmc.Text(
                            'docsLinkUrl="" — neither group',
                            size="sm",
                            fw=600,
                        ),
                        canvas_frame(
                            DashExcalidraw(
                                id="ui-links-none-canvas",
                                height="360px",
                                docsLinkUrl="",
                            ),
                            min_height=360,
                        ),
                    ],
                ),
            ],
        ),
    ],
)


@callback(
    Output("ui-options-canvas", "UIOptions"),
    # The overlay rides its own prop now. Sending it inside UIOptions as well
    # would be writing the mount-time key that never took effect — the very
    # thing that made this switch look dead.
    Output("ui-options-canvas", "welcomeScreen"),
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
        "welcomeScreen": False,
        "canvasActions": {
            "clearCanvas": bool(clear_),
            "export": bool(export),
            "loadScene": bool(load),
            "saveAsImage": bool(save_img),
            "toggleTheme": bool(tog_theme),
            "changeViewBackgroundColor": bool(change_bg),
        },
        "tools": {"image": bool(image)},
    }, bool(welcome)