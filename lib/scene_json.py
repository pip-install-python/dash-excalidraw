"""Raw scene JSON -> the commands that put it on a live canvas (/scene-viewer).

The page takes whatever a reader is holding — the scene JSON /trace-image
hands back, a `.excalidraw` file saved from excalidraw.com, a model's raw reply
on /ai-agent, a bare element array — and renders it. Everything that can be
decided without a browser is decided here, in pure Python, so the tests can
reach it without one:

* whether the text is a scene at all, and if not, a message saying why;
* what Excalidraw would throw away WITHOUT A WORD, said out loud first;
* the ordered commands that replace the canvas with the scene.

Why commands and not `initialData`: initialData is mount-only, which is
Excalidraw's rule before it is this component's. A second paste is a
post-mount change like any other, so it goes through the command dispatch.

Nothing here is part of the published dash-excalidraw package; it belongs to
the documentation site.
"""

from __future__ import annotations

import json
import uuid
from collections import Counter

from lib.scene_ai import _cleanup_json, _extract_json_block

# A `.excalidraw` file with a few inline photos is a few MB of base64; ten
# times that is a paste nobody meant to make, and it would travel through
# every command below.
MAX_SCENE_BYTES = 8 * 1024 * 1024

# The element types Excalidraw 0.18's `restoreElements` keeps. READ FROM THE
# PINNED BUNDLE, not recalled: its `restoreElement` switch handles exactly
# these, returns null for anything else, and `restoreElements` skips
# `selection` before the switch. "draw" is the legacy name it migrates to
# `line`. An element of any other type vanishes with nothing logged.
KNOWN_TYPES = frozenset({
    "rectangle", "ellipse", "diamond", "text", "arrow", "line", "draw",
    "freedraw", "image", "frame", "magicframe", "embeddable", "iframe",
})
LINEAR_TYPES = frozenset({"arrow", "line", "draw", "freedraw"})

# The appState a pasted scene may set. Everything else in a saved appState is
# either this component's to control (theme, viewModeEnabled, zen and grid
# mode are props, and a scene that set them would fight the props) or view
# state that `scrollToContent` recomputes anyway (scroll, zoom).
APPSTATE_KEYS = ("viewBackgroundColor", "gridSize", "gridStep")

# What an image file's `dataURL` may be for the canvas to load it: inline
# image bytes, or a URL (what `replaceFiles` leaves behind on /file-uploads).
# Not `data:text/html`, not `javascript:` — this string becomes an <img src>.
_LOADABLE_PREFIXES = ("data:image/", "https://", "http://", "/")


class SceneError(ValueError):
    """The text is not a scene this page can render. The message is for the
    reader, so it names the problem in their terms, not the parser's."""


def _strip_fences(text: str) -> str:
    """```json ... ``` -> the inside. Arrays as well as objects, which is why
    this is not `_extract_json_block` — that one looks for the first `{` and
    would return the first ELEMENT of a fenced array as if it were the scene."""
    t = text.strip()
    if t.startswith("```"):
        newline = t.find("\n")
        t = t[newline + 1:] if newline > 0 else ""
        t = t.rstrip()
        if t.endswith("```"):
            t = t[:-3]
    return t.strip()


def _loads(text: str):
    """json.loads, then the forgiving readings a model's reply needs."""
    try:
        return json.loads(text)
    except ValueError as exc:
        first = exc
    fenced = _strip_fences(text)
    for candidate in (
        fenced,
        _cleanup_json(fenced),
        # Prose around the object ("Here is your diagram: {...}").
        _cleanup_json(_extract_json_block(text)),
    ):
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    if isinstance(first, json.JSONDecodeError):
        raise SceneError(
            f"Not valid JSON: {first.msg} at line {first.lineno}, "
            f"column {first.colno}."
        ) from None
    raise SceneError("Not valid JSON.") from None


def parse_scene_text(text) -> dict:
    """Decode pasted or uploaded text into a scene dict with an `elements` list.

    Raises SceneError with a reader-facing message for anything else.
    """
    if text is None or not str(text).strip():
        raise SceneError("Nothing to render — paste scene JSON or upload a file.")
    text = str(text)
    size = len(text.encode("utf-8"))
    if size > MAX_SCENE_BYTES:
        raise SceneError(
            f"That is {size / 1024 / 1024:.1f} MB of JSON; the limit here is "
            f"{MAX_SCENE_BYTES // 1024 // 1024} MB. A scene that size is almost "
            f"always inline images — externalize them first (see File uploads)."
        )

    data = _loads(text)
    # `serializedData` is a JSON STRING, so a scene copied out of a dcc.Store,
    # a log line or a JSON dump arrives quoted once more than it should be.
    if isinstance(data, str):
        data = _loads(data)
    if isinstance(data, list):
        data = {"elements": data}
    if not isinstance(data, dict):
        raise SceneError(
            f"Expected a scene object or an array of elements; this JSON is "
            f"a {type(data).__name__}."
        )
    if data.get("type") == "excalidrawlib" or (
        "libraryItems" in data and "elements" not in data
    ):
        raise SceneError(
            "That is a library file (.excalidrawlib), not a scene. Libraries "
            "load through `updateLibrary` — see the Library page."
        )
    if "elements" not in data:
        raise SceneError(
            "This is JSON, but not an Excalidraw scene: there is no "
            "`elements` key."
        )
    if not isinstance(data["elements"], list):
        raise SceneError("`elements` has to be a list of element objects.")
    return data


def _invisibly_small(el: dict) -> bool:
    """Mirror of Excalidraw's `isInvisiblySmallElement`, which
    `restoreElements` uses to drop an element before it is ever drawn."""
    if el.get("type") in LINEAR_TYPES:
        points = el.get("points")
        return not isinstance(points, list) or len(points) < 2
    return el.get("width") == 0 and el.get("height") == 0


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def build_render(scene: dict, token: str | None = None) -> dict:
    """The commands that replace a canvas with `scene`, and what to tell the
    reader about it.

    Returns ``{"commands": [...], "drawn": int, "images": int, "notes": [...]}``.
    `commands` are in dispatch order and must go ONE AT A TIME — the canvas
    holds a single `command` and clears it when done, so a caller queues the
    tail and sends the next when it sees `command` go back to None.
    """
    token = token or uuid.uuid4().hex[:8]
    notes: list[str] = []

    kept: list[dict] = []
    not_objects = 0
    unknown: Counter = Counter()
    too_small = 0
    deleted = 0
    for el in scene.get("elements") or []:
        if not isinstance(el, dict):
            not_objects += 1
            continue
        kind = el.get("type")
        if kind not in KNOWN_TYPES:
            unknown[str(kind)] += 1
            continue
        if _invisibly_small(el):
            too_small += 1
            continue
        if el.get("isDeleted"):
            deleted += 1
        kept.append(el)

    ids = Counter(el.get("id") for el in kept if el.get("id"))
    duplicated = sum(n - 1 for n in ids.values() if n > 1)
    drawn = len(kept) - deleted

    # ---- files: which images can actually be shown -----------------------
    files = scene.get("files")
    if files is not None and not isinstance(files, dict):
        notes.append("`files` is not an object keyed by file id, so it was ignored.")
        files = None
    loadable: dict[str, dict] = {}
    for file_id, entry in (files or {}).items():
        if not isinstance(entry, dict):
            continue
        url = entry.get("dataURL")
        if isinstance(url, str) and url.startswith(_LOADABLE_PREFIXES):
            mime = entry.get("mimeType")
            if not mime and url.startswith("data:"):
                mime = url[5:].split(";", 1)[0].split(",", 1)[0]
            loadable[str(file_id)] = {"dataURL": url, "mimeType": mime or "image/png"}
    images = [el for el in kept if el.get("type") == "image" and not el.get("isDeleted")]
    no_bytes = sum(1 for el in images if el.get("fileId") not in loadable)

    # ---- what to say -----------------------------------------------------
    if not_objects:
        notes.append(f"{_plural(not_objects, 'entry')} in `elements` "
                     f"{'is' if not_objects == 1 else 'are'} not an object — skipped.")
    for kind, n in sorted(unknown.items()):
        label = "`selection`" if kind == "selection" else f"type `{kind}`"
        notes.append(f"{_plural(n, 'element')} of {label} skipped — Excalidraw "
                     f"drops that type on load without saying so.")
    if too_small:
        notes.append(f"{_plural(too_small, 'element')} skipped as invisibly small "
                     f"(zero width and height, or a line with fewer than two "
                     f"points) — Excalidraw would drop them too.")
    if deleted:
        notes.append(f"{_plural(deleted, 'element')} marked `isDeleted` "
                     f"{'is' if deleted == 1 else 'are'} kept in the scene but not drawn.")
    if duplicated:
        notes.append(f"{_plural(duplicated, 'duplicate id')} — Excalidraw gives "
                     f"each repeat a fresh random id, so an arrow bound to that "
                     f"id may attach to the other copy.")
    if no_bytes:
        notes.append(f"{_plural(no_bytes, 'image')} {'has' if no_bytes == 1 else 'have'} "
                     f"no loadable bytes (a `null` dataURL is what "
                     f"`externalizedSerializedData` leaves), so "
                     f"{'it draws' if no_bytes == 1 else 'they draw'} as an "
                     f"empty placeholder. Serve the file and point the scene at it — "
                     f"see File uploads.")
    if not drawn:
        notes.append("Nothing visible to draw — the canvas is cleared.")

    # ---- the commands, in order -----------------------------------------
    app_state = {}
    raw_state = scene.get("appState")
    if isinstance(raw_state, dict):
        app_state = {k: raw_state[k] for k in APPSTATE_KEYS if k in raw_state}

    commands = [
        # 1. A clean slate: elements, history and the previous scene's
        #    background. The component re-asserts its own mode props after.
        {"id": f"scene-{token}-reset", "type": "resetScene", "payload": {}},
        # 2. The scene. NEVER, so the first Ctrl+Z after loading does not
        #    unwind the whole load back to an empty canvas.
        {
            "id": f"scene-{token}-load",
            "type": "updateScene",
            "payload": {
                "elements": kept,
                "appState": app_state,
                "captureUpdate": "NEVER",
            },
        },
    ]
    if loadable:
        # 3. The image bytes. `replaceFiles`, not `addFiles`, on purpose:
        #    `addFiles` with an id the canvas already holds is a silent no-op
        #    (measured — see the component's replaceFiles comment), so the
        #    SECOND render of a scene, or a scene reusing an id with new bytes,
        #    would keep the old image. replaceFiles stores under a fresh id and
        #    repoints the image elements, which works every time.
        commands.append({
            "id": f"scene-{token}-files",
            "type": "replaceFiles",
            "payload": loadable,
        })
    if drawn:
        # 4. Frame it. fitToContent zooms OUT to fit and never in past 100%,
        #    so a tiny scene is not blown up to fill the canvas.
        commands.append({
            "id": f"scene-{token}-fit",
            "type": "scrollToContent",
            "payload": {"opts": {"fitToContent": True}},
        })

    return {
        "commands": commands,
        "drawn": drawn,
        "images": len(images),
        "notes": notes,
        "app_state": app_state,
    }
