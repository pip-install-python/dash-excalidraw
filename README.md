# dash-excalidraw

[Excalidraw](https://excalidraw.com/) drawing canvas for [Dash](https://dash.plotly.com/) 3+.

- Excalidraw `0.18.x` — elbow arrows, flowchart shortcuts, scene search, image cropping, element linking, command palette.
- Dash `3.0.3+`, Python `3.9+`, React `18.3.1`.
- JSON-safe prop surface: every prop round-trips cleanly through Dash callbacks.
- Imperative actions (export, scene updates, tool selection, …) via a `command`/`lastExport` round-trip.

See [`REBUILD.md`](./REBUILD.md) for the full rationale behind this rebuild.

---

## Install

```bash
pip install dash-excalidraw
```

Optionally, for the showcase app:

```bash
pip install "dash-excalidraw[demo]"
```

## Quickstart

```python
from dash import Dash
from dash_excalidraw import DashExcalidraw

app = Dash(__name__)
app.layout = DashExcalidraw(id="canvas", height="600px")

if __name__ == "__main__":
    app.run(debug=True)
```

## Running the showcase

```bash
pip install -e '.[demo,dev]'
npm install
npm run build       # builds the JS bundle + regenerates DashExcalidraw.py
python app.py
```

Then open <http://localhost:8050>. Each page under `pages/` demonstrates a single feature:

| Page | What it shows |
|---|---|
| `/basic` | Bare component with default props |
| `/initial-data` | Seeding elements, appState, and library on mount |
| `/theming` | `theme='light' | 'dark'` |
| `/view-modes` | `viewModeEnabled`, `zenModeEnabled`, `gridModeEnabled` |
| `/ui-options` | `UIOptions.canvasActions`, `welcomeScreen`, `tools.image` |
| `/events` | `lastPointerDown/Up/Move`, `lastScrollChange`, `lastPaste`, `lastLinkOpen` |
| `/commands` | Imperative `updateScene`, `setActiveTool`, `setToast`, `toggleSidebar`, … |
| `/export` | `exportToSvg` / `exportToBlob` / `exportToCanvas` round-trip |
| `/persistence` | `dcc.Store` autosave + restore via `updateScene` command |
| `/library` | `lastLibraryChange` + `updateLibrary` command |
| `/collaboration` | `isCollaborating` and `appState.collaborators` |
| `/file-uploads` | Externalize image blobs to HTTP URLs; strip base64 from JSON |

---

## Prop catalog

### Sizing

| Prop | Type | Default | Notes |
|---|---|---|---|
| `width` | `str` | `"100%"` | CSS value for the container |
| `height` | `str` | `"600px"` | Excalidraw fills its parent |

### Seeding the scene

| Prop | Type | Notes |
|---|---|---|
| `initialData` | `dict` | `{elements, appState, files, libraryItems, scrollToContent}`. Consumed once on mount. Use `command: updateScene` for post-mount changes. |

### Output state (read-only from Python)

These props are written by the component via `setProps`; do not write to them from Python.

| Prop | Type | Notes |
|---|---|---|
| `elements` | `list` | Current element array |
| `appState` | `dict` | Full serializable appState (zoom, scroll, active tool, collaborators, …) |
| `files` | `dict` | Binary file entries (images) |
| `serializedData` | `str` | Canonical Excalidraw JSON envelope — stream to `dcc.Store` for persistence |
| `externalizedSerializedData` | `str` | Same envelope, inline `data:` URIs stripped to `null`. Safe to persist without base64 bloat; pair with `replaceFiles` for external URLs |
| `sceneVersion` | `int` | Monotonic version counter from `getSceneVersion()` |

### Editor config (declarative)

| Prop | Type | Default |
|---|---|---|
| `viewModeEnabled` | `bool` | `False` |
| `zenModeEnabled` | `bool` | `False` |
| `gridModeEnabled` | `bool` | `False` |
| `isCollaborating` | `bool` | `False` |
| `theme` | `"light"` \| `"dark"` | `"light"` |
| `name` | `str` | — |
| `langCode` | `str` | `"en"` |
| `libraryReturnUrl` | `str` | — |
| `detectScroll` | `bool` | `True` |
| `handleKeyboardGlobally` | `bool` | `True` |
| `autoFocus` | `bool` | `True` |

### UIOptions

```python
UIOptions={
    "welcomeScreen": False,
    "canvasActions": {
        "changeViewBackgroundColor": True,
        "clearCanvas": True,
        "export": True,
        "loadScene": True,
        "saveToActiveFile": True,
        "saveAsImage": True,
        "toggleTheme": True,
    },
    "tools": {"image": True},
    "dockedSidebarBreakpoint": 960,
}
```

### Embeddable validation (no RegExp across the bridge)

Pass `True` / `False` / or a list of domain-glob strings. The component compiles them to case-insensitive `RegExp`s:

```python
validateEmbeddable=["*.youtube.com", "excalidraw.com", "*.github.com"]
```

### Event snapshot props

All written via `setProps`, carrying a `timestamp` so you can dedupe.

| Prop | Payload |
|---|---|
| `lastPointerDown` | `{timestamp, activeTool, pointer}` |
| `lastPointerUp` | `{timestamp, activeTool, pointer}` |
| `lastPointerMove` | `{timestamp, pointer, button}` — throttled by `pointerMoveThrottleMs` |
| `lastScrollChange` | `{timestamp, scrollX, scrollY}` — throttled by `scrollThrottleMs` |
| `lastPaste` | `{timestamp, data}` |
| `lastLibraryChange` | `{timestamp, items}` |
| `lastLinkOpen` | `{timestamp, elementId, url}` |
| `lastExport` | `{timestamp, id, type, result, error?}` — see "Command dispatch" |
| `lastFileAdded` | `{timestamp, fileId, mimeType, dataURL, size}` — fires once per new image (see "Images & files at scale") |

Throttles: `pointerMoveThrottleMs` (default `50`), `scrollThrottleMs` (default `100`).

### Command dispatch

Write to `command` to trigger an imperative action. Each command must carry a unique `id` — the component de-duplicates on `id` and clears the prop (`None`) once the action completes.

```python
@callback(Output("canvas", "command"),
          Input("btn", "n_clicks"),
          prevent_initial_call=True)
def export(_):
    return {"id": str(uuid.uuid4()),
            "type": "exportToSvg",
            "payload": {"exportPadding": 20}}
```

Supported types:

| `type` | `payload` | Result location |
|---|---|---|
| `updateScene` | `{elements?, appState?, files?, collaborators?, ...}` | — |
| `resetScene` | `{resetLoadingState?: bool}` | — |
| `addFiles` | `list[BinaryFileData]` | — |
| `scrollToContent` | `{target?, opts?: {fitToViewport, viewportZoomFactor}}` | — |
| `setActiveTool` | `{type, locked?, insertOnCanvasDirectly?}` | — |
| `setToast` | `{message, duration?, closable?}` | — |
| `toggleSidebar` | `{name, tab?, force?}` | — |
| `updateLibrary` | `{libraryItems, merge?, openLibraryMenu?, defaultStatus?}` | — |
| `replaceFiles` | `{[fileId]: {dataURL, mimeType?}}` | — (in-place overwrite; drops the old base64) |
| `exportToSvg` | [Excalidraw export opts] | `lastExport.result` = SVG markup string |
| `exportToBlob` | `{mimeType?, exportPadding?, ...}` | `lastExport.result` = data URL (base64) |
| `exportToCanvas` | same as above | `lastExport.result` = data URL |

Export round-trip:

```
Python                                           Component
──────                                           ─────────
command = {id, type='exportToSvg', payload}  ->  dispatch
                                            <-  lastExport = {id, type, result}
                                            <-  command = None
```

Match `lastExport.id` against the command you dispatched to correlate responses.

---

## Images & files at scale

Excalidraw stores every pasted or dropped image as a base64 `dataURL`
inside its `files` map. The serialized envelope bloats by 30–500× per
image — fine for a toy app, fatal for a production one where you'd be
jamming megabytes of base64 into Postgres or a `dcc.Store`.

The component exposes three hooks that collectively solve this without
forking Excalidraw:

1. **`lastFileAdded`** — fires with `{fileId, mimeType, dataURL, size}`
   the first time a new file appears. This is your "please upload me"
   signal.
2. **`replaceFiles` command** — dispatch `{[fileId]: {dataURL}}` with
   the URL you got back from your storage layer; Excalidraw overwrites
   its internal copy in-place and drops the old base64 bytes.
3. **`externalizedSerializedData`** — mirror of `serializedData` with
   every still-inline `data:` URI stripped to `null`. Persist this and
   the JSON stays tiny.

End-to-end flow:

```
User drops image                                    Excalidraw state
     │                                                    │
     ▼                                                    ▼
[Excalidraw stores base64 → onChange → lastFileAdded]     files: {fid: {dataURL: data:…}}
     │
     ▼
[Python callback]
  bytes = decode_data_url(event['dataURL'])
  url   = upload(bytes)          # ← your S3/disk/etc.
  return command=replaceFiles({fid: {dataURL: url}})
     │                                                    │
     ▼                                                    ▼
[Excalidraw addFiles overwrite → onChange re-fires]       files: {fid: {dataURL: url}}
     │
     ▼
externalizedSerializedData now contains the URL.          ← persist this, not serializedData
```

The package ships three Python helpers to complete the flow without
reinventing the base64 parsing yourself:

```python
from dash_excalidraw import (
    decode_data_url,         # (data_url) -> (mime_type, bytes)
    strip_inline_files,      # (serialized) -> (cleaner_serialized, {fileId: {dataURL, mimeType}})
    restore_inline_files,    # (serialized, {fileId: dataURL}) -> serialized
)
```

Run `python app.py` and open `/file-uploads` for a working reference
implementation — it uploads to an in-memory dict served by a Flask
route on the same Dash server. Swap `pages/_file_store.py` for your
real storage and the rest of the code is unchanged.

## Migrating from `0.0.x`

The public API has intentionally drifted. The delta is small but real.

| Old behavior | New behavior |
|---|---|
| `isCollaborating` default `True` | default `False` — set explicitly if you want the collaborator UI |
| `height` default `"400px"` | default `"600px"` |
| `appState` output contained just `{gridSize, viewBackgroundColor}` | Full serializable appState — strictly additive for pattern-matching callbacks |
| `onPointerUpdate`, `onPaste`, `onLibraryChange`, `onLinkOpen`, `onPointerDown`, `onScrollChange` | Removed (function props cannot cross the Dash bridge). Use `lastPointerMove`, `lastPaste`, `lastLibraryChange`, `lastLinkOpen`, `lastPointerDown`, `lastScrollChange` |
| `excalidrawAPI` callback prop | Removed. Use the `command` + `lastExport` round-trip |
| `validateEmbeddable: RegExp[]` | `validateEmbeddable: list[str]` (domain globs; JS compiles to RegExp) |

Not exposed (requires React children, not representable as JSON):

- `renderTopRightUI`, `renderCustomStats`, `renderEmbeddable`
- `generateIdForFile` (the component uses a UUID fallback)

Fork the wrapper if you need any of these — see `REBUILD.md` §4.3 for the full list.

---

## Development

```bash
# Python side
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev,demo]'

# JS side
npm install
npm run watch          # rebuild on change
npm run build:backends # regenerate DashExcalidraw.py after TS signature changes
```

Run the showcase with `python app.py`. Tests live in `tests/`.

## License

MIT — see [`LICENSE`](./LICENSE).