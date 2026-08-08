"""File uploads: externalize inline base64, place non-image placeholders,
auto-embed GIFs as animated iframes, view via dmc.Drawer.

Demonstrates the production pattern for keeping Excalidraw's serialized
JSON small and scalable, AND shows how the wrapper's extended drop
handler feeds multi-file and non-image cases through the same rails.

Flow per drop type:

  Image (non-GIF)
    wrapper adds as `image` element → lastFileAdded → Python uploads →
    replaceFiles swaps dataURL → JSON is clean.

  GIF
    wrapper adds as `image` element (static initially) → lastFileAdded
    → Python uploads → replaceFiles swaps dataURL → follow-up callback
    (triggered by `files`) spots the mime=image/gif with an external URL
    and replaces the image element with an `embeddable` so the GIF
    animates inside an iframe.

  Non-image (pdf, doc, csv, json, …)
    wrapper places a rectangle+text placeholder at the drop point →
    lastExternalDrop fires with {placeholderIds, files[]} → Python
    uploads → dispatches updateScene to set the placeholder's `link` to
    the served URL. Cmd/Ctrl+click opens the drawer.
"""

from __future__ import annotations

import json
import mimetypes
import uuid

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, ctx, dcc, html, no_update

from dash_excalidraw import DashExcalidraw, decode_data_url
from pages import _file_store
from pages._shared import (
    canvas_frame,
    code_block,
    page_header,
    sync_canvas_theme,
    two_column,
)

sync_canvas_theme("fu-canvas")

try:
    from dash import clientside_callback, ClientsideFunction  # noqa: F401
except ImportError:  # pragma: no cover
    clientside_callback = None
    ClientsideFunction = None

dash.register_page(
    __name__,
    path="/file-uploads",
    name="File uploads",
    description="External storage, GIF auto-embed, non-image drop + drawer",
    order=12,
)

# ---------------------------------------------------------------------------
# Showcase code snippet (trimmed for display)
# ---------------------------------------------------------------------------

FLOW_CODE = """
@callback(
    Output('canvas', 'command'),
    Output('uploads', 'data'),
    Input('canvas', 'lastFileAdded'),
    State('uploads', 'data'),
    prevent_initial_call=True,
)
def upload_and_swap(event, uploads):
    mappings = {}
    uploads = dict(uploads or {})
    for f in event.get('files') or [event]:
        mime, raw = decode_data_url(f['dataURL'])
        url = upload(raw, mime)     # ← your storage layer here
        uploads[f['fileId']] = {'url': url, 'mimeType': mime, ...}
        mappings[f['fileId']] = {'dataURL': url, 'mimeType': mime}
    return ({'id': str(uuid.uuid4()),
             'type': 'replaceFiles',
             'payload': mappings},
            uploads)
"""

# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------


def _human_bytes(n):
    if n is None:
        return "—"
    step = 1024.0
    n = float(n)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < step:
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} {unit}"
        n /= step
    return f"{n:.1f} TiB"


def _uploads_table(uploads):
    if not uploads:
        return dmc.Text(
            "Drop an image or any other file on the canvas to start.",
            size="sm",
            c="dimmed",
        )
    rows = []
    for fid, info in uploads.items():
        status = info.get("status", "uploaded")
        kind = info.get("kind", "image")
        rows.append(
            dmc.TableTr(
                [
                    dmc.TableTd(
                        dmc.Badge(
                            kind,
                            size="sm",
                            color={"gif": "grape", "file": "blue"}.get(kind, "teal"),
                            variant="light",
                        ),
                    ),
                    dmc.TableTd(
                        dmc.Code(
                            (info.get("name") or fid)[:22]
                            + ("…" if len(info.get("name") or fid) > 22 else "")
                        )
                    ),
                    dmc.TableTd(_human_bytes(info.get("size", 0))),
                    dmc.TableTd(
                        dmc.Anchor(
                            info.get("url", ""),
                            href=info.get("url", ""),
                            target="_blank",
                            size="xs",
                        )
                    ),
                    dmc.TableTd(
                        dmc.Badge(
                            status,
                            color="green" if status == "uploaded" else "yellow",
                            variant="light",
                            size="sm",
                        )
                    ),
                ]
            )
        )
    return dmc.Table(
        highlightOnHover=True,
        withTableBorder=True,
        children=[
            dmc.TableThead(
                dmc.TableTr(
                    [
                        dmc.TableTh("kind"),
                        dmc.TableTh("name"),
                        dmc.TableTh("size"),
                        dmc.TableTh("url"),
                        dmc.TableTh("status"),
                    ]
                )
            ),
            dmc.TableTbody(rows),
        ],
    )


def _size_panel(serialized, externalized):
    raw = len(serialized or "")
    ext = len(externalized or "")
    ratio = f"{raw / ext:.1f}×" if ext else "—"
    return dmc.Stack(
        gap="xs",
        children=[
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text("serializedData", size="sm", fw=500),
                    dmc.Badge(_human_bytes(raw), color="red", variant="light"),
                ],
            ),
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text("externalizedSerializedData", size="sm", fw=500),
                    dmc.Badge(_human_bytes(ext), color="green", variant="light"),
                ],
            ),
            dmc.Group(
                justify="space-between",
                children=[
                    dmc.Text("reduction", size="sm", c="dimmed"),
                    dmc.Text(ratio, size="sm", fw=600),
                ],
            ),
        ],
    )


def _emoji_for_mime(mime: str, name: str) -> str:
    """Python mirror of the TSX icon picker for the drawer header."""
    m = (mime or "").lower()
    n = (name or "").lower()
    if "pdf" in m or n.endswith(".pdf"):
        return "📕"
    if "csv" in m or n.endswith(".csv"):
        return "📊"
    if "spreadsheet" in m or "excel" in m or n.endswith((".xls", ".xlsx")):
        return "📊"
    if "presentation" in m or "powerpoint" in m or n.endswith((".ppt", ".pptx")):
        return "🎞️"
    if "msword" in m or "officedocument" in m or n.endswith((".doc", ".docx")):
        return "📘"
    if "json" in m or "yaml" in m or n.endswith((".json", ".yaml", ".yml", ".toml")):
        return "🗂️"
    if m.startswith("audio/"):
        return "🎵"
    if m.startswith("video/"):
        return "🎬"
    if m.startswith("image/"):
        return "🖼️"
    if "zip" in m or "tar" in m or "gzip" in m or "compressed" in m:
        return "🗜️"
    if m.startswith("text/"):
        return "📝"
    return "📎"


def _preview_for(file_id: str, mime: str, url: str):
    """Return a type-appropriate preview widget for the drawer body."""
    if mime.startswith("image/"):
        return html.Img(
            src=url,
            style={
                "maxWidth": "100%",
                "maxHeight": "55vh",
                "display": "block",
                "margin": "0 auto",
                "borderRadius": 8,
                "border": "1px solid var(--mantine-color-gray-3)",
            },
        )
    if mime == "application/pdf":
        return html.Iframe(
            src=url,
            style={
                "width": "100%",
                "height": "55vh",
                "border": "1px solid var(--mantine-color-gray-3)",
                "borderRadius": 8,
            },
        )
    if mime.startswith("text/") or mime in (
        "application/json",
        "application/xml",
        "application/javascript",
        "application/yaml",
        "application/x-yaml",
        "application/toml",
    ):
        entry = _file_store.get(file_id)
        text = ""
        try:
            text = entry[1].decode("utf-8", errors="replace") if entry else ""
        except Exception:
            text = "(cannot decode as UTF-8)"
        language = {
            "application/json": "json",
            "application/xml": "xml",
            "application/javascript": "javascript",
            "application/yaml": "yaml",
            "application/x-yaml": "yaml",
            "application/toml": "toml",
            "text/markdown": "markdown",
            "text/x-python": "python",
        }.get(mime, "text")
        try:
            return dmc.CodeHighlight(
                code=text[:20000],
                language=language,
                withCopyButton=True,
            )
        except Exception:
            return dmc.Code(text[:20000], block=True)
    return dmc.Alert(
        color="gray",
        variant="light",
        children=[
            dmc.Text(
                f"No inline preview available for {mime or 'this file type'}.",
                size="sm",
            ),
            dmc.Text(
                "Use the Download / Open buttons above to inspect the file.",
                size="xs",
                c="dimmed",
            ),
        ],
    )


def _drawer_body(file_id: str, name: str, mime: str, url: str):
    """Polished drawer layout: big icon header, metadata, actions, preview."""
    if not file_id:
        return dmc.Text("(no file selected)", c="dimmed")

    entry = _file_store.get(file_id)
    size_bytes = len(entry[1]) if entry else 0
    icon = _emoji_for_mime(mime, name)
    short_mime = (mime or "application/octet-stream").split("/")[-1].upper()

    header = dmc.Paper(
        withBorder=True,
        p="md",
        radius="md",
        children=dmc.Group(
            gap="md",
            wrap="nowrap",
            children=[
                dmc.Text(icon, style={"fontSize": 56, "lineHeight": 1}),
                dmc.Stack(
                    gap=4,
                    style={"flex": 1, "minWidth": 0},
                    children=[
                        dmc.Text(
                            name,
                            fw=700,
                            size="md",
                            style={
                                "overflow": "hidden",
                                "textOverflow": "ellipsis",
                                "whiteSpace": "nowrap",
                            },
                        ),
                        dmc.Group(
                            gap="xs",
                            children=[
                                dmc.Badge(
                                    short_mime,
                                    color="indigo",
                                    variant="light",
                                    size="sm",
                                ),
                                dmc.Text(
                                    _human_bytes(size_bytes),
                                    size="xs",
                                    c="dimmed",
                                ),
                                dmc.Text(
                                    f"id: {file_id[:14]}…"
                                    if len(file_id) > 14
                                    else f"id: {file_id}",
                                    size="xs",
                                    c="dimmed",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        ),
    )

    served_row = dmc.Paper(
        withBorder=True,
        p="sm",
        radius="md",
        children=dmc.Stack(
            gap=4,
            children=[
                dmc.Text("Served URL", size="xs", c="dimmed", fw=500),
                dmc.Group(
                    gap="xs",
                    wrap="nowrap",
                    children=[
                        dmc.Code(
                            url,
                            style={
                                "flex": 1,
                                "whiteSpace": "nowrap",
                                "overflow": "hidden",
                                "textOverflow": "ellipsis",
                            },
                        ),
                    ],
                ),
            ],
        ),
    )

    actions = dmc.Group(
        gap="xs",
        children=[
            html.A(
                dmc.Button(
                    "Download",
                    leftSection="⬇",
                    variant="filled",
                    color="indigo",
                ),
                href=url,
                download=name,
                style={"textDecoration": "none"},
            ),
            html.A(
                dmc.Button(
                    "Open in new tab",
                    leftSection="↗",
                    variant="light",
                ),
                href=url,
                target="_blank",
                rel="noreferrer",
                style={"textDecoration": "none"},
            ),
            dmc.Button(
                "Copy URL",
                id="fu-drawer-copy-btn",
                leftSection="⧉",
                variant="subtle",
                color="gray",
            ),
            dmc.Text(
                id="fu-drawer-copy-status",
                size="xs",
                c="green",
                style={"alignSelf": "center"},
            ),
        ],
    )

    preview_block = dmc.Paper(
        withBorder=True,
        p="md",
        radius="md",
        children=dmc.Stack(
            gap="xs",
            children=[
                dmc.Text("Preview", fw=600, size="sm"),
                _preview_for(file_id, mime, url),
            ],
        ),
    )

    return dmc.Stack(
        gap="md",
        children=[header, actions, served_row, preview_block],
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

layout = dmc.Stack(
    gap="md",
    children=[
        page_header(
            "File uploads",
            "Keep canvas JSON small: uploads to external storage, base64 "
            "swapped for URLs. Drop multiple images, or any non-image file, "
            "or a GIF — each takes the right path automatically.",
        ),
        dmc.Alert(
            color="indigo",
            variant="light",
            title="Drop anything",
            children=dmc.List(
                size="sm",
                children=[
                    dmc.ListItem(
                        "Single image → Excalidraw's native placement."
                    ),
                    dmc.ListItem(
                        "Multiple images → wrapper places them side-by-side and "
                        "`lastFileAdded` carries the full batch in `event['files']`."
                    ),
                    dmc.ListItem(
                        "GIF → uploaded, then the static image element is "
                        "upgraded to an `embeddable` iframe so the animation plays."
                    ),
                    dmc.ListItem(
                        "Any other file → rectangle placeholder on the canvas; "
                        "Cmd/Ctrl-click opens a drawer with its contents."
                    ),
                ],
            ),
        ),
        code_block(FLOW_CODE),
        dcc.Store(id="fu-uploads-store", data={}),
        dcc.Store(id="fu-drawer-store", data=None),
        two_column(
            canvas_frame(
                DashExcalidraw(
                    id="fu-canvas",
                    height="560px",
                    interceptLinkOpens=True,
                    validateEmbeddable=True,
                    UIOptions={
                        "welcomeScreen": False,
                        "tools": {"image": True},
                        "canvasActions": {"export": False, "saveAsImage": True},
                    },
                ),
                min_height=560,
            ),
            dmc.Stack(
                gap="md",
                children=[
                    dmc.Paper(
                        withBorder=True,
                        p="md",
                        children=dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text("Upload activity", fw=600),
                                dmc.Box(id="fu-table"),
                            ],
                        ),
                    ),
                    dmc.Paper(
                        withBorder=True,
                        p="md",
                        children=dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Text("Payload size", fw=600),
                                dmc.Box(id="fu-size"),
                            ],
                        ),
                    ),
                    dmc.Paper(
                        withBorder=True,
                        p="md",
                        children=dmc.Stack(
                            gap="xs",
                            children=[
                                dmc.Group(
                                    justify="space-between",
                                    children=[
                                        dmc.Text(
                                            "externalizedSerializedData",
                                            fw=600,
                                        ),
                                        dmc.Button(
                                            "Clear storage",
                                            id="fu-clear-btn",
                                            variant="subtle",
                                            color="red",
                                            size="compact-xs",
                                        ),
                                    ],
                                ),
                                dmc.ScrollArea(
                                    style={"height": 220},
                                    children=dmc.Code(
                                        id="fu-json",
                                        block=True,
                                        style={
                                            "whiteSpace": "pre-wrap",
                                            "wordBreak": "break-word",
                                            "fontSize": 11,
                                        },
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        ),
        dmc.Drawer(
            id="fu-drawer",
            opened=False,
            position="right",
            size="lg",
            padding="md",
            title=dmc.Group(
                [
                    dmc.Text(id="fu-drawer-title", fw=600),
                    dmc.Badge(id="fu-drawer-badge", size="sm", variant="light"),
                ]
            ),
            children=dmc.Box(id="fu-drawer-body"),
        ),
        dmc.Divider(label="Edge cases", labelPosition="center", my="lg"),
        dmc.SimpleGrid(
            cols={"base": 1, "md": 3},
            spacing="md",
            children=[
                dmc.Card(
                    withBorder=True,
                    p="md",
                    children=dmc.Stack(
                        gap="xs",
                        children=[
                            dmc.Text("Multi-file drag-drop", fw=600),
                            dmc.Text(
                                "Drop several files (any mix of types). The "
                                "wrapper places them all side-by-side and "
                                "`lastFileAdded` carries the full batch in "
                                "`event['files']`.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ),
                dmc.Card(
                    withBorder=True,
                    p="md",
                    children=dmc.Stack(
                        gap="xs",
                        children=[
                            dmc.Text("GIF auto-embed", fw=600),
                            dmc.Text(
                                "Canvas rasterization freezes GIFs. We upload, "
                                "then swap the image element for an embeddable "
                                "so the iframe renders the animation natively.",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ),
                dmc.Card(
                    withBorder=True,
                    p="md",
                    children=dmc.Stack(
                        gap="xs",
                        children=[
                            dmc.Text("Non-image files", fw=600),
                            dmc.Text(
                                "PDF, JSON, CSV, anything — placed on the "
                                "canvas as a card. Cmd/Ctrl-click opens the "
                                "drawer with a type-appropriate view (iframe, "
                                "syntax highlight, or download).",
                                size="sm",
                                c="dimmed",
                            ),
                        ],
                    ),
                ),
            ],
        ),
    ],
)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


@callback(
    Output("fu-canvas", "command"),
    Output("fu-uploads-store", "data"),
    Input("fu-canvas", "lastFileAdded"),
    State("fu-uploads-store", "data"),
    prevent_initial_call=True,
)
def _upload_and_swap(event, uploads):
    """Upload every new file in the batch; dispatch replaceFiles once."""
    if not event:
        return no_update, no_update
    files_in_event = event.get("files") or [
        {k: event.get(k) for k in ("fileId", "mimeType", "dataURL", "size")}
    ]
    uploads = dict(uploads or {})
    mappings = {}
    for f in files_in_event:
        try:
            mime, raw = decode_data_url(f["dataURL"])
        except (ValueError, KeyError):
            continue
        url = _file_store.put(f["fileId"], mime, raw)
        uploads[f["fileId"]] = {
            "url": url,
            "size": f.get("size", len(raw)),
            "mimeType": mime,
            "name": f.get("fileId"),
            "kind": "gif" if mime == "image/gif" else "image",
            "status": "uploaded",
        }
        mappings[f["fileId"]] = {"dataURL": url, "mimeType": mime}
    if not mappings:
        return no_update, no_update
    return (
        {
            "id": f"replace-{uuid.uuid4()}",
            "type": "replaceFiles",
            "payload": mappings,
        },
        uploads,
    )


@callback(
    Output("fu-canvas", "command", allow_duplicate=True),
    Input("fu-canvas", "files"),
    State("fu-canvas", "elements"),
    prevent_initial_call=True,
)
def _upgrade_gifs_to_embeddable(files, elements):
    """Once a GIF has an external URL, swap its image element for an iframe."""
    if not files or not elements:
        return no_update
    gif_targets = []
    for el in elements:
        if el.get("type") != "image":
            continue
        fid = el.get("fileId")
        if not fid:
            continue
        entry = files.get(fid) if isinstance(files, dict) else None
        if not isinstance(entry, dict):
            continue
        if entry.get("mimeType") != "image/gif":
            continue
        url = entry.get("dataURL")
        if not isinstance(url, str) or url.startswith("data:"):
            continue
        gif_targets.append(
            {
                "id": el["id"],
                "x": el.get("x", 0),
                "y": el.get("y", 0),
                "width": el.get("width", 320),
                "height": el.get("height", 240),
                "url": url,
            }
        )
    if not gif_targets:
        return no_update

    target_ids = {g["id"] for g in gif_targets}
    new_elements = [el for el in elements if el["id"] not in target_ids]
    now_ms = int(uuid.uuid4().int % (10**12))
    for g in gif_targets:
        # Use the /viewer HTML wrapper as the embeddable src. Pointing the
        # iframe directly at the raw GIF URL trips Chromium's same-URL frame
        # safety check ("Unsafe attempt to load URL ... from frame with URL ...");
        # loading HTML that contains an <img> sidesteps that and lets the GIF
        # animate natively inside the iframe.
        viewer_href = g["url"].rstrip("/") + "/viewer"
        new_elements.append(
            {
                "id": f"gif-embed-{g['id']}",
                "type": "embeddable",
                "x": g["x"],
                "y": g["y"],
                "width": g["width"],
                "height": g["height"],
                "angle": 0,
                "strokeColor": "transparent",
                "backgroundColor": "transparent",
                "fillStyle": "solid",
                "strokeWidth": 1,
                "strokeStyle": "solid",
                "roughness": 0,
                "opacity": 100,
                "seed": now_ms % 1_000_000,
                "version": 1,
                "versionNonce": now_ms % 1_000_000,
                "isDeleted": False,
                "groupIds": [],
                "frameId": None,
                "boundElements": [],
                "updated": now_ms,
                "link": viewer_href,
                "locked": False,
                "roundness": None,
            }
        )
    return {
        "id": f"gif-upgrade-{uuid.uuid4()}",
        "type": "updateScene",
        "payload": {"elements": new_elements},
    }


@callback(
    Output("fu-canvas", "command", allow_duplicate=True),
    Output("fu-uploads-store", "data", allow_duplicate=True),
    Input("fu-canvas", "lastExternalDrop"),
    State("fu-canvas", "elements"),
    State("fu-uploads-store", "data"),
    prevent_initial_call=True,
)
def _handle_external_drop(event, elements, uploads):
    """Non-image drops: upload each file and set the placeholder's link."""
    if not event or not event.get("files"):
        return no_update, no_update
    placeholder_ids = event.get("placeholderIds") or []
    uploads = dict(uploads or {})
    updates = {}  # elementId -> {link, mimeType, fileId, name}
    for idx, f in enumerate(event["files"]):
        try:
            mime, raw = decode_data_url(f["dataURL"])
        except (ValueError, KeyError):
            continue
        # Use a single store_key for everything: file_store, uploads dict,
        # and customData.external.fileId. Keeps the drawer lookup honest.
        guessed_ext = mimetypes.guess_extension(mime) or ""
        store_key = f"ext-{uuid.uuid4().hex[:12]}{guessed_ext}"
        url = _file_store.put(store_key, mime, raw)
        uploads[store_key] = {
            "url": url,
            "size": f.get("size", len(raw)),
            "mimeType": mime,
            "name": f.get("name") or store_key,
            "kind": "file",
            "status": "uploaded",
        }
        if idx < len(placeholder_ids):
            updates[placeholder_ids[idx]] = {
                "link": url,
                "fileId": store_key,
                "mimeType": mime,
                "name": f.get("name") or store_key,
            }
    if not updates:
        return no_update, uploads

    # Update matching placeholder rectangles with link (+ sidecar metadata)
    new_elements = []
    for el in elements or []:
        meta = updates.get(el.get("id"))
        if meta and el.get("type") == "rectangle":
            patched = dict(el)
            patched["link"] = meta["link"]
            # Stash metadata in customData so the drawer callback can look up
            # mime/name/fileId by element id without re-parsing the link.
            patched["customData"] = {
                **(el.get("customData") or {}),
                "external": meta,
            }
            new_elements.append(patched)
        else:
            new_elements.append(el)

    return (
        {
            "id": f"extdrop-{uuid.uuid4()}",
            "type": "updateScene",
            "payload": {"elements": new_elements},
        },
        uploads,
    )


@callback(
    Output("fu-drawer", "opened"),
    Output("fu-drawer-title", "children"),
    Output("fu-drawer-badge", "children"),
    Output("fu-drawer-body", "children"),
    Output("fu-drawer-store", "data"),
    Input("fu-canvas", "lastLinkOpen"),
    State("fu-canvas", "elements"),
    prevent_initial_call=True,
)
def _open_drawer(link_event, elements):
    """Open the drawer when a placeholder link is clicked."""
    if not link_event or not link_event.get("elementId"):
        return no_update, no_update, no_update, no_update, no_update
    eid = link_event["elementId"]
    url = link_event.get("url") or ""
    # Only handle links served from our Flask endpoint
    if not url.startswith(_file_store.FILE_URL_PREFIX):
        return no_update, no_update, no_update, no_update, no_update
    target = next((el for el in (elements or []) if el.get("id") == eid), None)
    meta = (target or {}).get("customData", {}).get("external", {})
    name = meta.get("name") or url.rsplit("/", 1)[-1]
    mime = meta.get("mimeType") or "application/octet-stream"
    file_id = meta.get("fileId") or url.rsplit("/", 1)[-1]
    body = _drawer_body(file_id, name, mime, url)
    return True, name, mime, body, {"url": url, "name": name, "mime": mime}


@callback(
    Output("fu-table", "children"),
    Input("fu-uploads-store", "data"),
)
def _render_table(uploads):
    return _uploads_table(uploads)


@callback(
    Output("fu-size", "children"),
    Output("fu-json", "children"),
    Input("fu-canvas", "serializedData"),
    Input("fu-canvas", "externalizedSerializedData"),
)
def _render_size(serialized, externalized):
    size_panel = _size_panel(serialized, externalized)
    if not externalized:
        json_blob = "(draw or drop something to see the envelope)"
    else:
        try:
            json_blob = json.dumps(json.loads(externalized), indent=2)
        except (TypeError, ValueError):
            json_blob = externalized
    return size_panel, json_blob


@callback(
    Output("fu-uploads-store", "data", allow_duplicate=True),
    Input("fu-clear-btn", "n_clicks"),
    prevent_initial_call=True,
)
def _clear_store(_clicks):
    _file_store.clear()
    return {}


if clientside_callback is not None:
    clientside_callback(
        """
        function(n, data) {
            if (!n || !data || !data.url) { return window.dash_clientside.no_update; }
            try {
                const href = new URL(data.url, window.location.origin).href;
                navigator.clipboard.writeText(href);
                return "copied ✓";
            } catch (err) {
                return "copy failed";
            }
        }
        """,
        Output("fu-drawer-copy-status", "children"),
        Input("fu-drawer-copy-btn", "n_clicks"),
        State("fu-drawer-store", "data"),
        prevent_initial_call=True,
    )