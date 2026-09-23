"""Scene viewer: paste or upload raw scene JSON and render it on a live canvas.

The other half of /trace-image. That page hands a trace back as scene JSON;
this one takes scene JSON — a trace, a `.excalidraw` file, a model's reply, a
bare element array — and draws it. No model is called, so nothing here spends
anything and the page works on a deployment with no provider keys.

The parsing and the "what will Excalidraw silently drop" checks live in
lib/scene_json.py so they can be tested without a browser. What is left here
is the one thing a Dash page has to get right: the canvas takes ONE command at
a time, and a render is four of them.
"""

from __future__ import annotations

import base64
import binascii
import json
import uuid

import dash
import dash_mantine_components as dmc
from dash import Input, Output, State, callback, clientside_callback, dcc, no_update

from dash_excalidraw import DashExcalidraw
from docs._shared import canvas_frame, sync_canvas_theme
from lib.scene_json import MAX_SCENE_BYTES, SceneError, build_render, parse_scene_text

sync_canvas_theme("scene-viewer-canvas")


# ---------------------------------------------------------------------------
#  The sample — hand-written, in the shape /trace-image hands back
# ---------------------------------------------------------------------------
#
# NOT a real trace, and labelled as such on the page: it is a small scene
# written to the same envelope `externalizedSerializedData` produces, so the
# textarea opens on something a reader can edit and re-render straight away.

def _base(el_id, kind, x, y, width, height, stroke="#1e1e1e", bg="transparent",
          seed=1, **extra):
    return {
        "id": el_id, "type": kind, "x": x, "y": y,
        "width": width, "height": height, "angle": 0,
        "strokeColor": stroke, "backgroundColor": bg, "fillStyle": "solid",
        "strokeWidth": 2, "strokeStyle": "solid", "roughness": 1,
        "opacity": 100, "groupIds": [], "frameId": None,
        "roundness": {"type": 3} if kind in ("rectangle", "diamond") else (
            {"type": 2} if kind == "ellipse" else None),
        "seed": seed, "version": 1, "versionNonce": seed, "isDeleted": False,
        "boundElements": [], "updated": 1, "link": None, "locked": False,
        **extra,
    }


def _text(el_id, text, cx, cy, size=16, color="#1e1e1e", container=None, seed=1):
    lines = text.split("\n")
    width = round(max(len(line) for line in lines) * size * 0.6)
    height = round(size * 1.25 * len(lines))
    return _base(
        el_id, "text", round(cx - width / 2), round(cy - height / 2), width, height,
        stroke=color, seed=seed, text=text, originalText=text, fontSize=size,
        fontFamily=2, textAlign="center",
        verticalAlign="middle" if container else "top",
        containerId=container, lineHeight=1.25, autoResize=True,
    )


def _box(el_id, kind, label, x, y, stroke, bg, seed):
    """A shape with its label bound inside it, both halves of the binding set."""
    w, h = 200, 80
    shape = _base(el_id, kind, x, y, w, h, stroke=stroke, bg=bg, seed=seed,
                  boundElements=[{"id": f"{el_id}-label", "type": "text"}])
    label_el = _text(f"{el_id}-label", label, x + w / 2, y + h / 2,
                     color=stroke, container=el_id, seed=seed + 100)
    return shape, label_el


def _arrow(el_id, start, end, x, y, dx, dy, seed):
    return _base(
        el_id, "arrow", x, y, abs(dx), abs(dy), seed=seed,
        points=[[0, 0], [dx, dy]], lastCommittedPoint=None,
        startBinding={"elementId": start, "focus": 0, "gap": 4},
        endBinding={"elementId": end, "focus": 0, "gap": 4},
        startArrowhead=None, endArrowhead="arrow", elbowed=False,
    )


def _sample_scene() -> dict:
    ref, ref_label = _box("ref", "rectangle", "Reference image",
                          60, 140, "#4263eb", "#dbe4ff", 11)
    model, model_label = _box("model", "ellipse", "Vision model",
                              380, 140, "#0ca678", "#c3fae8", 21)
    scene_json, scene_label = _box("json", "rectangle", "Scene JSON",
                                   700, 140, "#e67700", "#ffe8cc", 31)
    viewer, viewer_label = _box("viewer", "rectangle", "This canvas",
                                700, 320, "#ae3ec9", "#eebefa", 41)
    arrows = [
        _arrow("a1", "ref", "model", 264, 180, 112, 0, 51),
        _arrow("a2", "model", "json", 584, 180, 112, 0, 52),
        _arrow("a3", "json", "viewer", 800, 224, 0, 92, 53),
    ]
    # Each arrow is listed on both shapes it binds, or dragging a shape
    # leaves the arrow behind.
    for arrow in arrows:
        for shape in (ref, model, scene_json, viewer):
            if shape["id"] in (arrow["startBinding"]["elementId"],
                               arrow["endBinding"]["elementId"]):
                shape["boundElements"].append({"id": arrow["id"], "type": "arrow"})

    title = _text("title", "Trace → scene JSON → canvas", 480, 60, size=28,
                  color="#1e3a8a", seed=61)
    caption = _text(
        "caption",
        "A hand-written sample in the shape /trace-image hands back.\n"
        "Edit the JSON, or replace it with your own, and press Render.",
        300, 380, size=14, color="#6b7280", seed=62,
    )
    caption["textAlign"] = "left"
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.2plot.dev/scene-viewer",
        "elements": [title, ref, ref_label, model, model_label, scene_json,
                     scene_label, viewer, viewer_label, *arrows, caption],
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
        "files": {},
    }


SAMPLE_SCENE = _sample_scene()
SAMPLE_TEXT = json.dumps(SAMPLE_SCENE, indent=2)


# ---------------------------------------------------------------------------
#  Layout
# ---------------------------------------------------------------------------

component = dmc.Stack(
    gap="sm",
    children=[
        # STACKED, not side by side. The canvas IS the output, and in this
        # site's content column (sidebar left, table of contents right) a
        # 7/12 column left it about 300px wide — too narrow to read a trace.
        dmc.Textarea(
            id="scene-viewer-input",
            label="Scene JSON",
            description=(
                "A trace from /trace-image, a .excalidraw file, a model's reply, "
                "or a bare element array"
            ),
            value=SAMPLE_TEXT,
            autosize=False,
            # DMC 2.8 rejects `spellcheck=` as a kwarg; Mantine's `attributes`
            # reaches the <textarea>. Without it every key in the JSON is
            # underlined red.
            attributes={"input": {"spellCheck": "false"}},
            styles={
                "input": {
                    "fontFamily": "var(--mantine-font-family-monospace)",
                    "fontSize": 12,
                    "height": 260,
                }
            },
            **{"aria-label": "Scene JSON to render"},
        ),
        dmc.Group(
            gap="xs",
            children=[
                dmc.Button("Render", id="scene-viewer-render", color="indigo"),
                dcc.Upload(
                    id="scene-viewer-upload",
                    multiple=False,
                    accept=".json,.excalidraw,application/json",
                    max_size=MAX_SCENE_BYTES,
                    children=dmc.Button("Upload file", variant="light", color="indigo"),
                ),
                dmc.Button(
                    "Canvas → JSON", id="scene-viewer-pull", variant="light", color="gray"
                ),
                dmc.Button("Sample", id="scene-viewer-sample", variant="subtle", color="gray"),
                dmc.Button("Clear", id="scene-viewer-clear", variant="subtle", color="gray"),
            ],
        ),
        dmc.Alert(
            id="scene-viewer-status",
            color="gray",
            variant="light",
            children=(
                "Showing the sample. Paste a scene over it, or upload a .json / "
                ".excalidraw file."
            ),
        ),
        canvas_frame(
            DashExcalidraw(
                id="scene-viewer-canvas",
                height="560px",
                # The FIRST scene only. initialData is mount-only; every render
                # after this one is the command queue below.
                initialData=SAMPLE_SCENE,
            ),
            min_height=560,
        ),
        # The commands still to send, in order. See `_next_command`.
        dcc.Store(id="scene-viewer-queue", data=[]),
        # Whether the opening scene has been fitted yet. See `_fit_once`.
        dcc.Store(id="scene-viewer-fitted", data=False),
    ],
)


# ---------------------------------------------------------------------------
#  Callbacks
# ---------------------------------------------------------------------------


def _decode_upload(contents: str, filename: str | None) -> str:
    """A dcc.Upload data URL -> the file's text."""
    if not contents or "," not in contents:
        raise SceneError("The upload arrived empty.")
    try:
        raw = base64.b64decode(contents.split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        raise SceneError(f"{filename or 'That file'} could not be read.") from None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SceneError(
            f"{filename or 'That file'} is not text. A scene is a .json or "
            f".excalidraw file; a PNG with an embedded scene is not supported here."
        ) from None


def _rich(text: str) -> list:
    """`backticked` spans as inline code. The notes are written for a reader,
    in lib/scene_json.py, with backticks round the names they quote."""
    parts = str(text).split("`")
    return [dmc.Code(part) if i % 2 else part for i, part in enumerate(parts) if part]


def _summary(render: dict) -> str:
    drawn = render["drawn"]
    parts = [f"{drawn} element{'' if drawn == 1 else 's'} drawn"]
    if render["images"]:
        parts.append(f"{render['images']} image{'' if render['images'] == 1 else 's'}")
    background = render["app_state"].get("viewBackgroundColor")
    if background:
        parts.append(f"background {background}")
    return " · ".join(parts)


@callback(
    Output("scene-viewer-canvas", "command", allow_duplicate=True),
    Output("scene-viewer-queue", "data"),
    Output("scene-viewer-input", "value"),
    Output("scene-viewer-status", "children"),
    Output("scene-viewer-status", "color"),
    Output("scene-viewer-status", "title"),
    Input("scene-viewer-render", "n_clicks"),
    Input("scene-viewer-upload", "contents"),
    Input("scene-viewer-sample", "n_clicks"),
    Input("scene-viewer-clear", "n_clicks"),
    State("scene-viewer-upload", "filename"),
    State("scene-viewer-input", "value"),
    prevent_initial_call=True,
)
def _render(_render, upload, _sample, _clear, filename, text):
    """Parse whatever the reader supplied and start the command queue.

    Sends the FIRST command and parks the rest in the Store; `_next_command`
    feeds them to the canvas one at a time.
    """
    trigger = dash.ctx.triggered_id
    if trigger == "scene-viewer-clear":
        return (
            {"id": f"scene-clear-{uuid.uuid4().hex[:8]}",
             "type": "resetScene", "payload": {}},
            [], "", "Canvas cleared.", "gray", None,
        )

    new_text = no_update
    source = "the pasted JSON"
    try:
        if trigger == "scene-viewer-upload":
            text = new_text = _decode_upload(upload, filename)
            source = filename or "the uploaded file"
        elif trigger == "scene-viewer-sample":
            text = new_text = SAMPLE_TEXT
            source = "the sample"
        render = build_render(parse_scene_text(text))
    except SceneError as exc:
        return (no_update, no_update, new_text, dmc.Text(_rich(exc), size="sm"),
                "red", f"Could not render {source}")

    first, *rest = render["commands"]
    notes = render["notes"]
    body = dmc.Stack(gap=4, children=[dmc.Text(_summary(render), size="sm")] + [
        dmc.Text(["• ", *_rich(note)], size="sm") for note in notes
    ])
    return (
        first, rest, new_text, body,
        "yellow" if notes else "green",
        f"Rendered {source}" + (" — with notes" if notes else ""),
    )


@callback(
    Output("scene-viewer-canvas", "command"),
    Output("scene-viewer-queue", "data", allow_duplicate=True),
    Input("scene-viewer-canvas", "command"),
    State("scene-viewer-queue", "data"),
    prevent_initial_call=True,
)
def _next_command(current, queue):
    """Feed the canvas the next queued command once it has finished the last.

    THE CANVAS HOLDS ONE COMMAND. It runs it, then sets `command` back to None
    — and that write is this callback's trigger. Returning four commands from
    one callback is not an option (each would overwrite the last before it
    ran), so a render is a queue: `_render` sends the head, and every time the
    canvas reports itself idle this sends the next. When the queue is empty
    it does nothing, which is how the chain ends.

    `current` is not None when the trigger was a callback SETTING a command
    rather than the canvas clearing one; that is not our turn.
    """
    if current is not None or not queue:
        return no_update, no_update
    head, *rest = queue
    return head, rest


@callback(
    Output("scene-viewer-input", "value", allow_duplicate=True),
    Output("scene-viewer-status", "children", allow_duplicate=True),
    Output("scene-viewer-status", "color", allow_duplicate=True),
    Output("scene-viewer-status", "title", allow_duplicate=True),
    Input("scene-viewer-pull", "n_clicks"),
    State("scene-viewer-canvas", "serializedData"),
    prevent_initial_call=True,
)
def _pull(_clicks, serialized):
    """The canvas as it is now — tidied, edited, whatever — back into the box.

    `serializedData`, not `externalizedSerializedData`: this is a round trip,
    and the externalized form nulls every inline image, so pulling a scene
    with pictures in it and rendering it again would lose them.
    """
    if not serialized:
        return no_update, "The canvas has not reported a scene yet — draw something first.", "gray", None
    try:
        scene = json.loads(serialized)
    except (TypeError, ValueError):
        return no_update, "The canvas produced no readable scene.", "red", None
    count = len([e for e in scene.get("elements") or [] if not e.get("isDeleted")])
    return (
        json.dumps(scene, indent=2),
        f"Copied the canvas into the box — {count} element{'' if count == 1 else 's'}.",
        "gray",
        None,
    )


# THE OPENING SCENE, FITTED ONCE. `initialData.scrollToContent` only centres
# the scene, it does not zoom, and a fit command cannot go at page load: the
# API the command waits for exists before Excalidraw has finished loading
# initialData, so it would frame an empty scene. The first `elements` write
# with content IS the "scene loaded" signal.
#
# Even that can be too early on its own. The app shell applies the table of
# contents' offset AFTER first paint — a callback sets the aside, and main's
# padding-right then transitions 32px -> 312px over 200ms — so the canvas
# narrows under a fit already sent. MEASURED on a 1728px viewport: 1316px wide
# before the offset, 1036px after, with the fit going out at 1036 once this
# wait was in. Excalidraw keeps its scroll through a resize, so a fit framed
# for the wider canvas leaves the scene off-centre with its right edge cut
# off. The fit waits until the canvas has held one width for 300ms (capped at
# 2s).
# Clientside, because it is one command, and deciding "already done" on the
# server would cost a round trip per canvas change.
clientside_callback(
    """
    async function(elements, fitted) {
        const skip = window.dash_clientside.no_update;
        if (fitted || !elements || !elements.length) { return [skip, skip]; }
        const box = document.getElementById("scene-viewer-canvas");
        const began = performance.now();
        let width = -1, steadySince = began;
        while (box && performance.now() - began < 2000) {
            const now = box.getBoundingClientRect().width;
            if (now !== width) { width = now; steadySince = performance.now(); }
            else if (performance.now() - steadySince > 300) { break; }
            await new Promise((done) => setTimeout(done, 50));
        }
        return [
            {id: "scene-opening-fit", type: "scrollToContent",
             payload: {opts: {fitToContent: true}}},
            true,
        ];
    }
    """,
    Output("scene-viewer-canvas", "command", allow_duplicate=True),
    Output("scene-viewer-fitted", "data"),
    Input("scene-viewer-canvas", "elements"),
    State("scene-viewer-fitted", "data"),
    prevent_initial_call=True,
)
