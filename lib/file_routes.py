"""Routes that serve blobs held by :mod:`lib.file_store`.

These used to live in the demo's own ``app.py``. That file is gone — the site
now boots from ``run.py`` on the network boilerplate — so they live here and
are registered explicitly, which also means the /file-uploads page keeps
working under every backend rather than only under Flask.

Nothing here is required by the published ``dash-excalidraw`` package. The
component emits bytes and accepts URLs; where those URLs point is entirely the
host application's business. This module is one worked answer, sized for a
demo.
"""

from __future__ import annotations

import io

from lib import file_store

# Wrapper served for Excalidraw `embeddable` elements. Pointing the iframe at
# a raw GIF URL trips a Chromium same-URL frame-safety check; wrapping the
# asset in a tiny HTML viewer sidesteps that and lets animated GIFs actually
# animate inside the canvas.
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


def _viewer_body(mime: str, src: str) -> str:
    if mime.startswith("image/"):
        return f'<img src="{src}" alt="">'
    if mime == "application/pdf":
        return f'<iframe src="{src}"></iframe>'
    return f'<div class="note">Preview not available for {mime}.</div>'


def register(app) -> bool:
    """Attach the blob routes to ``app``'s underlying server.

    Returns the backend name it attached on, or False.

    THIS MODULE WAS DEAD CODE until 2026-09-12: nothing imported it, so the
    routes existed on no backend at all. MEASURED on the running app —
    ``GET /excalidraw-files/nope`` answered 200 with the site's HTML, because
    Dash's page router caught it. Every externalized upload therefore pointed
    at the SPA shell rather than at its bytes, and /file-uploads' GIF
    auto-embed loaded that shell into an iframe instead of an animation.

    FastAPI is supported as well as Flask/Quart, because the local dev backend
    here IS FastAPI. The old docstring said FastAPI "degrades to Excalidraw's
    own inline copies, which is a visual no-op" — that was wrong twice over:
    nothing registered these on Flask either, and the degradation is not a
    no-op when a page's whole point is externalizing the bytes.
    """
    server = getattr(app, "server", None)
    if server is None:
        return False

    route = getattr(server, "route", None)
    if route is not None and not _is_fastapi(server):
        _register_wsgi(route)
        return "flask"

    if _is_fastapi(server):
        _register_asgi(server)
        return "fastapi"

    return False


def _is_fastapi(server) -> bool:
    """FastAPI also exposes ``.route``, with different semantics.

    Its decorator is ``add_api_route``-shaped and its path params use
    ``{name}`` rather than ``<name>``, so handing it a Flask rule registers
    a route nobody can reach. Sniff for a FastAPI-only attribute instead of
    trusting ``route``.
    """
    return hasattr(server, "add_api_route") or hasattr(server, "openapi")


def _register_asgi(server) -> None:
    from fastapi import Response
    from fastapi.responses import HTMLResponse

    @server.get(f"{file_store.FILE_URL_PREFIX}/{{file_id}}")
    def _serve_file_asgi(file_id: str):
        entry = file_store.get(file_id)
        if not entry:
            # Expiry lands here too: a blob past its TTL is simply gone.
            return Response(status_code=404)
        mime, data = entry
        return Response(content=data, media_type=mime)

    @server.get(f"{file_store.FILE_URL_PREFIX}/{{file_id}}/viewer")
    def _serve_viewer_asgi(file_id: str):
        entry = file_store.get(file_id)
        if not entry:
            return Response(status_code=404)
        mime, _ = entry
        body = _viewer_body(mime, f"{file_store.FILE_URL_PREFIX}/{file_id}")
        return HTMLResponse(_VIEWER_HTML.format(body=body))


def _register_wsgi(route) -> None:

    @route(f"{file_store.FILE_URL_PREFIX}/<file_id>")
    def _serve_excalidraw_file(file_id: str):
        from flask import abort, send_file

        entry = file_store.get(file_id)
        if not entry:
            # Also the expiry path: a blob past its TTL is simply gone, and
            # 404 is the honest answer.
            return abort(404)
        mime, data = entry
        return send_file(
            io.BytesIO(data),
            mimetype=mime,
            as_attachment=False,
            download_name=file_id,
        )

    @route(f"{file_store.FILE_URL_PREFIX}/<file_id>/viewer")
    def _serve_excalidraw_viewer(file_id: str):
        from flask import abort

        entry = file_store.get(file_id)
        if not entry:
            return abort(404)
        mime, _ = entry
        body = _viewer_body(mime, f"{file_store.FILE_URL_PREFIX}/{file_id}")
        return (
            _VIEWER_HTML.format(body=body),
            200,
            {"Content-Type": "text/html; charset=utf-8"},
        )
