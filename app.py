"""dash-excalidraw showcase app.

Run:
    python app.py

Each page in `pages/` demonstrates a single feature area of
`dash_excalidraw.DashExcalidraw` with a runnable, isolated example.
"""

import io
import secrets

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, clientside_callback, dcc, html
from flask import abort, send_file

from pages import _file_store

# Optional SocketIO — only available when the [colab] extra is installed.
# When missing, the /ai-colab page renders a "install dash-socketio" banner
# instead of crashing the whole app.
try:
    from flask_socketio import SocketIO

    from pages._colab_server import register_socketio_handlers

    _HAS_SOCKETIO = True
except ImportError:
    SocketIO = None  # type: ignore[assignment]
    register_socketio_handlers = None  # type: ignore[assignment]
    _HAS_SOCKETIO = False

# Mantine v2 ships its own stylesheets that must be on every page.
_stylesheets = [
    "https://unpkg.com/@mantine/core@7.11.0/styles.css",
    "https://unpkg.com/@mantine/dates@7.11.0/styles.css",
    "https://unpkg.com/@mantine/code-highlight@7.11.0/styles.css",
    "https://unpkg.com/@mantine/charts@7.11.0/styles.css",
    "https://unpkg.com/@mantine/carousel@7.11.0/styles.css",
    "https://unpkg.com/@mantine/notifications@7.11.0/styles.css",
    "https://unpkg.com/@mantine/nprogress@7.11.0/styles.css",
]

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=_stylesheets,
    suppress_callback_exceptions=True,
    title="dash-excalidraw showcase",
)

server = app.server
# flask-socketio requires a secret_key; for the demo a per-run random is
# fine (no session data survives restart).
server.secret_key = secrets.token_hex(32)

# ----------------------------------------------------------------------
# SocketIO instance for /ai-colab. Threading async mode so we don't need
# eventlet / gevent. cors_allowed_origins is broad for the demo — tighten
# to your real origin(s) in production.
# ----------------------------------------------------------------------
socketio = None
if _HAS_SOCKETIO:
    socketio = SocketIO(
        server,
        cors_allowed_origins="*",
        async_mode="threading",
    )
    register_socketio_handlers(socketio)


# ----------------------------------------------------------------------
# Flask routes backing the /file-uploads demo. In production these are
# replaced by S3/GCS signed URLs or a CDN — the Dash-side contract
# (URLs returned from uploads, fed back via `replaceFiles`) is the same.
# ----------------------------------------------------------------------
@server.route(f"{_file_store.FILE_URL_PREFIX}/<file_id>")
def _serve_excalidraw_file(file_id: str):
    entry = _file_store.get(file_id)
    if not entry:
        return abort(404)
    mime, data = entry
    return send_file(
        io.BytesIO(data),
        mimetype=mime,
        as_attachment=False,
        download_name=file_id,
    )


# HTML wrapper used by Excalidraw `embeddable` elements. Pointing the iframe
# at a raw GIF URL trips a Chromium same-URL frame-safety check; wrapping
# the asset in a tiny HTML viewer sidesteps that and lets animated GIFs
# actually animate inside the canvas.
_VIEWER_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
html,body {{ margin:0; padding:0; height:100%; background:#fff; }}
body {{ display:flex; align-items:center; justify-content:center; overflow:hidden; }}
img {{ max-width:100%; max-height:100%; object-fit:contain; }}
iframe {{ width:100%; height:100%; border:0; }}
.note {{ font-family:system-ui; color:#666; padding:16px; }}
</style></head>
<body>{body}</body></html>
"""


@server.route(f"{_file_store.FILE_URL_PREFIX}/<file_id>/viewer")
def _serve_excalidraw_viewer(file_id: str):
    entry = _file_store.get(file_id)
    if not entry:
        return abort(404)
    mime, _ = entry
    src = f"{_file_store.FILE_URL_PREFIX}/{file_id}"
    if mime.startswith("image/"):
        body = f'<img src="{src}" alt="">'
    elif mime == "application/pdf":
        body = f'<iframe src="{src}"></iframe>'
    else:
        body = f'<div class="note">Preview not available for {mime}.</div>'
    return _VIEWER_HTML.format(body=body), 200, {"Content-Type": "text/html; charset=utf-8"}


# ----------------------------------------------------------------------
# Shell
# ----------------------------------------------------------------------
def _nav_link(page: dict) -> dmc.NavLink:
    return dmc.NavLink(
        label=page["name"],
        href=page["relative_path"],
        description=page.get("description", ""),
        style={"borderRadius": 6},
    )


def _sidebar() -> dmc.ScrollArea:
    ordered = sorted(dash.page_registry.values(), key=lambda p: p.get("order", 99))
    links = [_nav_link(p) for p in ordered]
    return dmc.ScrollArea(
        type="scroll",
        offsetScrollbars=True,
        style={"height": "calc(100vh - 60px)"},
        children=dmc.Stack(links, gap="xs", p="sm"),
    )


def _header() -> dmc.Group:
    return dmc.Group(
        justify="space-between",
        align="center",
        h="100%",
        px="md",
        children=[
            dmc.Group(
                gap="sm",
                children=[
                    dmc.ThemeIcon(
                        "EX",
                        size=34,
                        radius="md",
                        variant="gradient",
                        gradient={"from": "indigo", "to": "cyan", "deg": 90},
                    ),
                    dmc.Stack(
                        gap=0,
                        children=[
                            dmc.Text(
                                "dash-excalidraw",
                                fw=700,
                                size="lg",
                            ),
                            dmc.Text(
                                "feature showcase · v0.1.0",
                                c="dimmed",
                                size="xs",
                            ),
                        ],
                    ),
                ],
            ),
            dmc.Group(
                gap="sm",
                children=[
                    dmc.Anchor(
                        "REBUILD.md",
                        href="https://github.com/pip-install-python/dash-excalidraw/blob/main/REBUILD.md",
                        target="_blank",
                        size="sm",
                    ),
                    dmc.ActionIcon(
                        id="color-scheme-toggle",
                        size="lg",
                        variant="default",
                        children=dmc.Text("☀️", size="lg"),
                    ),
                ],
            ),
        ],
    )


app.layout = dmc.MantineProvider(
    id="mantine-provider",
    defaultColorScheme="light",
    theme={
        "primaryColor": "indigo",
        "fontFamily": "Inter, system-ui, sans-serif",
        "defaultRadius": "md",
    },
    children=dmc.AppShell(
        header={"height": 60},
        navbar={
            "width": 280,
            "breakpoint": "sm",
            "collapsed": {"mobile": True, "desktop": False},
        },
        padding="md",
        children=[
            dmc.AppShellHeader(_header()),
            dmc.AppShellNavbar(_sidebar()),
            dmc.AppShellMain(
                dmc.Container(
                    dash.page_container,
                    size="xl",
                    py="md",
                )
            ),
            dcc.Store(id="color-scheme-store", data="light"),
        ],
    ),
)


# ----------------------------------------------------------------------
# Color scheme toggle
# ----------------------------------------------------------------------
@callback(
    Output("color-scheme-store", "data"),
    Input("color-scheme-toggle", "n_clicks"),
    State("color-scheme-store", "data"),
    prevent_initial_call=True,
)
def _toggle_scheme(_n, current):
    return "dark" if current == "light" else "light"


clientside_callback(
    """
    function(scheme) {
        return scheme;
    }
    """,
    Output("mantine-provider", "forceColorScheme"),
    Input("color-scheme-store", "data"),
)


if __name__ == "__main__":
    if socketio is not None:
        # flask-socketio owns the event loop when present. `allow_unsafe_
        # werkzeug=True` lets us keep using Dash's werkzeug dev server;
        # production should front this with gunicorn + eventlet/gevent.
        socketio.run(
            server,
            debug=True,
            port=8053,
            allow_unsafe_werkzeug=True,
        )
    else:
        app.run(debug=True, port=8053)