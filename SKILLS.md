---
name: dash-excalidraw
description: Use this skill when building or modifying Dash apps that embed `dash_excalidraw.DashExcalidraw` — an Excalidraw drawing canvas bound to Dash via a JSON-safe prop surface. Covers the command/event pattern for imperative actions, file externalization for image uploads, persistence, theming, AI-driven scene generation, and multiplayer collaboration.
---

# dash-excalidraw — Skill Guide

This is a **base component** for drawing canvases in Dash 3+ apps. It wraps
Excalidraw (`0.17.6` pinned; `0.18.x`-ready per `REBUILD.md`) and exposes
everything through props that can round-trip cleanly through Dash
callbacks — no `func` props, no React children, no RegExp, just JSON.

---

## When to use this skill

- You're adding a drawing / whiteboard / diagram canvas to a Dash app.
- You're migrating code off the old `dash-excalidraw 0.0.x` API.
- You need to drive Excalidraw imperatively from a Python callback (scene
  updates, tool switches, exports).
- You're wiring AI-generated scenes into the canvas.
- You're building multi-user collaboration on top of the canvas.
- You're debugging why something the old package did "just worked" now
  needs explicit plumbing — chances are it's now a *command* or an
  *event*.

If the user only needs a static image or a plain HTML `<canvas>`, this is
the wrong tool.

---

## Core mental model

### Three kinds of props

| Kind | Direction | Mechanics |
|---|---|---|
| **Declarative** | Python → canvas | Set it, canvas reflects it: `theme`, `viewModeEnabled`, `zenModeEnabled`, `gridModeEnabled`, `isCollaborating`, `UIOptions`, `validateEmbeddable`, `interceptLinkOpens`, `hideExcalidrawLinks`, `langCode`, `name`. |
| **Event snapshot (output-only)** | canvas → Python | Read via `Input`, never write from Python: `elements`, `appState`, `files`, `serializedData`, `externalizedSerializedData`, `sceneVersion`, `lastPointerDown/Up/Move`, `lastScrollChange`, `lastPaste`, `lastLibraryChange`, `lastLinkOpen`, `lastExport`, `lastFileAdded`, `lastExternalDrop`. |
| **Command dispatch** | Python → canvas (imperative) | Write `{id, type, payload}` to `command`. Component dispatches exactly once per unique `id`, then clears the prop. Use for anything that used to live on the removed `excalidrawAPI` callback. |

### Command dispatch pattern

Any time you want to "do something now" to the canvas from Python:

```python
@callback(
    Output("canvas", "command"),
    Input("go-btn", "n_clicks"),
    prevent_initial_call=True,
)
def dispatch(_):
    return {
        "id": f"cmd-{uuid.uuid4()}",   # MUST be unique; drives de-dup
        "type": "updateScene",         # see table below
        "payload": {...},              # shape depends on type
    }
```

Supported `type` values — group them in three buckets:

| Scene mutation | Async export (round-trips via `lastExport`) | Other |
|---|---|---|
| `updateScene` | `exportToSvg` | `setActiveTool` |
| `resetScene` | `exportToBlob` | `setToast` |
| `addFiles` | `exportToCanvas` | `toggleSidebar` |
| `replaceFiles` | | `updateLibrary` |
| `scrollToContent` | | |

### Event-and-command round-trip (exports)

Exports are async. The pattern:

```python
# 1. dispatch
return {"id": "export-42", "type": "exportToSvg", "payload": {"exportPadding": 20}}

# 2. observe — SEPARATE callback
@callback(Output("preview", "children"), Input("canvas", "lastExport"))
def render(result):
    if result and result["id"] == "export-42" and result["type"] == "exportToSvg":
        return html.Iframe(srcDoc=result["result"])
```

**Always match on `id`.** Async exports can arrive out of order under load.

---

## Install + boot

```bash
pip install dash-excalidraw
```

Optional extras:

- `dash-excalidraw[demo]` — `dash-mantine-components` for the showcase app shell
- `dash-excalidraw[ai]` — `anthropic`, `google-genai` for the AI agent page
- `dash-excalidraw[colab]` — `flask-socketio`, `dash-socketio` for multiplayer

Minimal app:

```python
from dash import Dash
from dash_excalidraw import DashExcalidraw

app = Dash(__name__)
app.layout = DashExcalidraw(id="canvas", height="600px")
app.run(debug=True)
```

---

## Canonical recipes

### 1. Sync scene to a `dcc.Store` (persistence)

```python
import json, uuid
from dash import Input, Output, State, callback, dcc, no_update

layout = html.Div([
    DashExcalidraw(id="canvas"),
    dcc.Store(id="store", storage_type="session"),
    dmc.Button("Restore", id="restore-btn"),
])

# Save — GUARD against the mount-time empty scene or you'll wipe a
# valid snapshot on every page refresh.
@callback(
    Output("store", "data"),
    Input("canvas", "serializedData"),
    prevent_initial_call=True,
)
def save(serialized):
    if not serialized:
        return no_update
    parsed = json.loads(serialized)
    if not parsed.get("elements"):
        return no_update
    return serialized

# Restore — use updateScene, NOT initialData (initialData is mount-only).
@callback(
    Output("canvas", "command"),
    Input("restore-btn", "n_clicks"),
    State("store", "data"),
    prevent_initial_call=True,
)
def restore(_, snapshot):
    if not snapshot:
        return no_update
    parsed = json.loads(snapshot)
    return {
        "id": f"restore-{uuid.uuid4()}",
        "type": "updateScene",
        "payload": {
            "elements": parsed.get("elements", []),
            "appState": parsed.get("appState", {}),
        },
    }
```

### 2. Externalize image files (the big production win)

`files[*].dataURL` holds base64 by default — a single image can bloat the
scene JSON by 100–500×. Use the upload-and-swap pattern:

```python
import uuid
from dash_excalidraw import DashExcalidraw, decode_data_url

@callback(
    Output("canvas", "command"),
    Output("uploads-store", "data"),
    Input("canvas", "lastFileAdded"),
    State("uploads-store", "data"),
    prevent_initial_call=True,
)
def upload_and_swap(event, uploads):
    # `event.files` carries the whole batch of new files; iterate it.
    mappings = {}
    uploads = dict(uploads or {})
    for f in event.get("files") or [event]:
        mime, raw = decode_data_url(f["dataURL"])
        url = my_upload(raw, mime)         # ← your S3/GCS/disk
        uploads[f["fileId"]] = {"url": url, "mime": mime, "size": f["size"]}
        mappings[f["fileId"]] = {"dataURL": url, "mimeType": mime}
    return (
        {"id": f"replace-{uuid.uuid4()}", "type": "replaceFiles", "payload": mappings},
        uploads,
    )
```

After the swap, persist `externalizedSerializedData` instead of
`serializedData` — it has all inline `data:` URIs stripped to `null`.

Helpers: `dash_excalidraw.decode_data_url`, `strip_inline_files`,
`restore_inline_files`.

### 3. Drop anything (non-image files)

The wrapper's drop handler places a card-style placeholder on the canvas
for non-image files and emits `lastExternalDrop`:

```python
@callback(
    Output("canvas", "command"),
    Input("canvas", "lastExternalDrop"),
    State("canvas", "elements"),
    prevent_initial_call=True,
)
def stamp_link(event, elements):
    # After uploading event.files, set `link` on the placeholder rectangles.
    placeholder_ids = event.get("placeholderIds", [])
    updates = {}
    for idx, f in enumerate(event["files"]):
        url = my_upload(*decode_data_url(f["dataURL"]))
        if idx < len(placeholder_ids):
            updates[placeholder_ids[idx]] = {"link": url, "name": f["name"], ...}
    # Rewrite matched rectangles in place
    new_elements = [
        {**el, "link": updates[el["id"]]["link"], "customData": {"external": updates[el["id"]]}}
        if el["id"] in updates else el
        for el in (elements or [])
    ]
    return {"id": ..., "type": "updateScene", "payload": {"elements": new_elements}}
```

Pair with `interceptLinkOpens=True` to capture clicks and open a
`dmc.Drawer` instead of navigating.

### 4. AI-generated scenes

See `pages/ai_agent.py` for the reference. Key points:

- **Stream** the model call — `client.messages.stream(...)` with
  `.get_final_message()` on Anthropic SDK; `response_mime_type="application/json"`
  on Gemini. Non-streaming blows through the sync HTTP budget when
  `max_tokens` goes above ~16K.
- Use the **command dispatch** pattern — dispatch `updateScene` with the
  parsed elements + appState + files. Do **not** rebuild the component via
  `key=`. That was a 0.0.x workaround for missing imperative API; it's
  obsolete.
- Run AI output through a string-aware bracket matcher, not a non-greedy
  regex — nested JSON will trick `\{[\s\S]*?\}` into truncating.
- Surface truncation explicitly: check `final.stop_reason == "max_tokens"`
  (Claude) and `candidates[0].finish_reason` (Gemini).

### 5. Theming (follow app color scheme)

```python
# Shared store
dcc.Store(id="color-scheme-store", data="light")

# Ship the current scheme into every canvas' theme prop
clientside_callback(
    "function(scheme) { return scheme || 'light'; }",
    Output("canvas", "theme"),
    Input("color-scheme-store", "data"),
)
```

### 6. GIF embeds (animation)

Canvas-rasterized images don't animate. Upload the GIF, then replace the
`image` element with an `embeddable` pointing at a viewer URL that wraps
the GIF in HTML:

```python
# After normal image upload + replaceFiles has run with a mime=image/gif
# See pages/file_uploads.py:_upgrade_gifs_to_embeddable for the full pattern.
new_elements.append({
    "id": f"gif-embed-{image_element_id}",
    "type": "embeddable",
    "x": old.x, "y": old.y, "width": old.w, "height": old.h,
    "link": f"/excalidraw-files/{file_id}/viewer",  # HTML wrapper route
    ...
})
```

---

## Gotchas (read before you swear at it)

1. **`initialData` is mount-only.** Setting it after render does nothing.
   Use `command: updateScene` for post-mount changes.
2. **`externalizedSerializedData` != `serializedData`.** The former has
   base64 stripped; persist the former, transmit the latter.
3. **Commands must have unique `id` fields.** Same id = no dispatch.
   `uuid.uuid4()` every time.
4. **`lastExport` isn't the result of your latest command** — it's the
   result of *some* export. Match `lastExport["id"]` against the command
   you dispatched.
5. **`appState.collaborators`** expects a `Map` in Excalidraw's internals;
   the wrapper converts plain Python dicts automatically inside the
   `updateScene` command handler. Don't try to build a `Map` yourself.
6. **Text elements created programmatically render invisibly** until
   Excalidraw measures them. The wrapper runs new elements through
   `restoreElements` inside the `updateScene` command handler to fix
   this, but if you're dispatching elements *outside* that path, do it
   yourself or they'll only appear after a user clicks/resizes them.
7. **Scene sync during drag** interferes with in-flight draft elements.
   If you're building multiplayer, gate `updateScene` dispatches on a
   "pointer-down" state store — see `pages/ai_colab.py`.
8. **Mount-time empty scene.** Excalidraw's first `onChange` on mount is
   an empty envelope. If you're broadcasting to peers or saving to a
   store, skip empty envelopes or you'll clobber real state on page
   refresh.
9. **`welcomeScreen` is mount-state.** Toggling the prop after first
   interaction won't bring it back — Excalidraw internal, not a bug.

---

## Migrating from `0.0.x`

Short migration table:

| Old | New |
|---|---|
| `onPointerUpdate`, `onPaste`, `onLibraryChange`, `onLinkOpen`, `onPointerDown`, `onScrollChange` | `lastPointerMove`, `lastPaste`, `lastLibraryChange`, `lastLinkOpen`, `lastPointerDown`, `lastScrollChange` |
| `excalidrawAPI` callback | `command` prop + `lastExport` event |
| `isCollaborating` defaulted `True` | defaults `False` — opt in explicitly |
| `height` defaulted `"400px"` | defaults `"600px"` |
| `appState` output: `{gridSize, viewBackgroundColor}` only | full serializable appState |
| `validateEmbeddable: RegExp[]` | `validateEmbeddable: list[str]` (domain globs, compiled to RegExps internally) |

Anything declared as `PropTypes.func` in the old package is gone —
function props can't round-trip through JSON. Use the event/command
replacements above.

---

## Where to look for examples

All runnable, all in `pages/`:

| File | Demonstrates |
|---|---|
| `basic.py` | Minimum viable usage |
| `initial_data.py` | Seeding the scene on mount |
| `theming.py` | `theme` prop |
| `view_modes.py` | `viewModeEnabled` / `zenModeEnabled` / `gridModeEnabled` |
| `ui_options.py` | `UIOptions.canvasActions` toggles + `welcomeScreen` quirk |
| `events.py` | All `last*` event snapshot props |
| `commands.py` | Command dispatch (tools, sidebar, toast, scroll, scene) |
| `export.py` | `exportToSvg` / `exportToBlob` round-trip |
| `persistence.py` | `dcc.Store` save/restore with empty-scene guard |
| `library.py` | `lastLibraryChange` + `updateLibrary` command |
| `collaboration.py` | `isCollaborating` + collaborator pointer |
| `file_uploads.py` | Full externalization: upload → `replaceFiles` → drawer |
| `ai_agent.py` | Claude/Gemini → scene JSON via `updateScene` |
| `ai_colab.py` | SocketIO multiplayer + persistent AI buddy + auto-tidy |

Authoritative architectural reference: `REBUILD.md` at repo root.
Full prop catalog: `README.md`.

---

## Non-goals (don't try these)

- **`renderTopRightUI`, `renderCustomStats`, `renderEmbeddable`.** These
  require React children, not representable as JSON. Fork the wrapper
  if you need them.
- **Self-hosted fonts.** Excalidraw 0.18 loads fonts from `esm.run` CDN
  by default. Offline environments see fallback fonts. Planned for 0.2.0
  as an opt-in prop.
- **Built-in collaboration transport.** `isCollaborating` + `collaborators`
  state are exposed, but the wrapper ships no WebSocket/CRDT backend.
  See `pages/ai_colab.py` for a flask-socketio reference.
- **Animated GIFs as `image` elements.** Canvas rasterization freezes
  them. Use `embeddable` + viewer wrapper HTML page (see recipe 6).

---

## One-line summaries the model should internalize

- If you're tempted to add a `PropTypes.func` prop, use an event-snapshot
  prop + command dispatch instead.
- If a user asks "how do I sync the scene to a DB", the answer is
  `serializedData` + `externalizedSerializedData` + `replaceFiles`.
- If a user asks "how do I have the AI draw something", the answer is
  `command: updateScene` + a model call with `response_mime_type: json`
  or the string-aware JSON extractor.
- If a user asks "why is my text invisible until I click it", the answer
  is `restoreElements` — and if they're dispatching via `command:
  updateScene`, the wrapper already does this.
- If a user asks "why did my canvas empty on refresh", the answer is the
  mount-time empty-scene guard.