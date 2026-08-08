"""Landing page: project overview and quick navigation."""

import dash
import dash_mantine_components as dmc

dash.register_page(
    __name__,
    path="/",
    name="Overview",
    description="What dash-excalidraw is and what's on each page",
    order=0,
)


def _feature_card(title: str, body: str, href: str) -> dmc.Anchor:
    return dmc.Anchor(
        href=href,
        underline=False,
        children=dmc.Card(
            withBorder=True,
            shadow="xs",
            radius="md",
            p="md",
            children=dmc.Stack(
                gap=4,
                children=[
                    dmc.Text(title, fw=600),
                    dmc.Text(body, size="sm", c="dimmed"),
                ],
            ),
        ),
    )


layout = dmc.Stack(
    gap="lg",
    children=[
        dmc.Title("dash-excalidraw", order=1),
        dmc.Text(
            "Excalidraw 0.18 bound to Dash 3+ with a JSON-safe prop surface. "
            "Every page in the sidebar is a runnable feature example — open one "
            "to see the prop wired up and try it live.",
            size="md",
            c="dimmed",
        ),
        dmc.Alert(
            color="indigo",
            variant="light",
            title="Rebuild in progress (v0.1.0)",
            children=dmc.Text(
                [
                    "This rebuild breaks with 0.0.x by design. See ",
                    dmc.Anchor(
                        "REBUILD.md",
                        href="https://github.com/pip-install-python/dash-excalidraw/blob/main/REBUILD.md",
                        target="_blank",
                    ),
                    " for the full rationale. The new prop surface replaces the "
                    "dead function props (onPointerUpdate, excalidrawAPI, ...) with "
                    "setProps-powered event snapshots and a command dispatch prop.",
                ],
                size="sm",
            ),
        ),
        dmc.Title("Explore", order=3),
        dmc.SimpleGrid(
            cols={"base": 1, "sm": 2, "lg": 3},
            spacing="md",
            children=[
                _feature_card(
                    "Basic usage",
                    "The minimum: render a canvas with default props.",
                    "/basic",
                ),
                _feature_card(
                    "initialData",
                    "Seed the scene with elements, appState, and files on mount.",
                    "/initial-data",
                ),
                _feature_card(
                    "Theming",
                    "Light/dark switch synced with the app shell.",
                    "/theming",
                ),
                _feature_card(
                    "View modes",
                    "viewModeEnabled, zenModeEnabled, gridModeEnabled.",
                    "/view-modes",
                ),
                _feature_card(
                    "UIOptions",
                    "Toggle individual canvas actions and the welcome screen.",
                    "/ui-options",
                ),
                _feature_card(
                    "Events",
                    "Observe pointer/scroll/paste via the last* snapshot props.",
                    "/events",
                ),
                _feature_card(
                    "Command dispatch",
                    "Drive Excalidraw imperatively from Python via the command prop.",
                    "/commands",
                ),
                _feature_card(
                    "Export",
                    "Export to SVG, PNG blob, or canvas via the command round-trip.",
                    "/export",
                ),
                _feature_card(
                    "Persistence",
                    "Save scene to dcc.Store and restore on reload.",
                    "/persistence",
                ),
                _feature_card(
                    "Library",
                    "Observe and drive library items (custom shapes).",
                    "/library",
                ),
                _feature_card(
                    "Collaboration",
                    "isCollaborating flag and appState.collaborators scaffolding.",
                    "/collaboration",
                ),
                _feature_card(
                    "File uploads",
                    "Strip base64 from the JSON; serve images externally.",
                    "/file-uploads",
                ),
                _feature_card(
                    "AI agent",
                    "Prompt → scene via Claude or Gemini; side-by-side compare.",
                    "/ai-agent",
                ),
                _feature_card(
                    "AI collab",
                    "Multiplayer canvas + resident Claude-bot (Phase 1: presence).",
                    "/ai-colab",
                ),
            ],
        ),
    ],
)