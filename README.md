<div align="center">

<a href="https://2plot.ai">
  <img src="https://cdn.2plot.ai/github_assets/android-chrome-512x512.png" alt="dash-excalidraw" width="120">
  <img src="https://cdn.2plot.ai/github_assets/dark_mode_2plot.png" alt="2plot.ai" width="300">
</a>


# dash-excalidraw

**dash-excalidraw — Excalidraw drawing canvas for Dash**

The [Excalidraw](https://excalidraw.com/) whiteboard as a first-class component for [Plotly Dash](https://dash.plotly.com) 3 and 4.

Every prop JSON-serializable · events arrive as timestamped snapshot props · imperative actions via a `command`/`lastExport` round-trip · image externalization built in · no `clientside_callback` required for anything.

[![PyPI version](https://img.shields.io/pypi/v/dash-excalidraw?color=blue)](https://pypi.org/project/dash-excalidraw/)
[![Python](https://img.shields.io/pypi/pyversions/dash-excalidraw)](https://pypi.org/project/dash-excalidraw/)
[![Dash 3+](https://img.shields.io/badge/Dash-3%2B%20%7C%204.x-1a1a2e?logo=plotly&logoColor=white)](https://dash.plotly.com/)
[![Excalidraw 0.18.1](https://img.shields.io/badge/Excalidraw-0.18.1-6741d9)](https://github.com/excalidraw/excalidraw)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Discord](https://img.shields.io/badge/Discord-Join-5865F2?logo=discord&logoColor=white)](https://discord.gg/WEnZR35mrK)
[![YouTube](https://img.shields.io/badge/YouTube-%402plotai-FF0000?logo=youtube&logoColor=white)](https://www.youtube.com/channel/UC6Bmo0t0ZUpU_xKBYW0bJuQ)

**[Documentation](https://excalidraw.2plot.dev)** · [Discord](https://discord.gg/WEnZR35mrK) · [YouTube](https://www.youtube.com/channel/UC6Bmo0t0ZUpU_xKBYW0bJuQ) · [GitHub](https://github.com/pip-install-python/dash-excalidraw)

<br/>

<a href="https://excalidraw.2plot.dev">
  <img src="https://cdn.2plot.ai/github_assets/excalidraw.2plot.dev.png" alt="dash-excalidraw running live at excalidraw.2plot.dev" width="880">
</a>

_Live at **[excalidraw.2plot.dev](https://excalidraw.2plot.dev)** — every canvas on the docs site is a running Dash app._

<br/>

_Maintained by **[Pip Install Python LLC](https://github.com/2plotai)**._

</div>

---

## Overview

Excalidraw is a React application with a large imperative API. Wrapping it for Dash means
answering one question honestly: **what crosses the Python/JavaScript bridge?**

Only JSON crosses. Functions, RegExps and class instances do not. Most wrappers give up at
that point and hand you a `clientside_callback` for anything interesting. This one doesn't —
it translates the whole surface into three JSON-safe patterns:

| Upstream shape | What Python sees | Why |
|---|---|---|
| Callbacks (`onPaste`, `onPointerUpdate`, …) | **Snapshot props** — `lastPaste`, `lastPointerMove`, … each carrying a `timestamp` | A callback cannot be serialized. A record of it firing can. The timestamp lets you dedupe. |
| Imperative methods (`updateScene`, `exportToSvg`, …) | **`command`** — `{id, type, payload}`, dispatched once per unique `id` | One prop covers twelve methods, and re-renders can't re-fire a command. |
| Async results (exports) | **`lastExport`**, keyed by the `id` you dispatched | Exports resolve out of order under load. The id is how you correlate. |
| `validateEmbeddable` RegExp | A **list of glob strings**, compiled to case-insensitive RegExps on the JS side | A RegExp has no JSON representation. `"*.youtube.com"` does. |

The result is that a Dash developer writes ordinary `@callback`s and never touches
JavaScript.

## Installation

```bash
pip install dash-excalidraw
```

Nothing else is required — the Excalidraw bundle, its stylesheet and its UI font ship
inside the wheel as a single self-contained JavaScript file. There is no CDN dependency at
load time, no `external_stylesheets` entry to add, and no build step for consumers.

## Quick Start

```python
from dash import Dash, Input, Output, callback, html
from dash_excalidraw import DashExcalidraw

app = Dash(__name__)

app.layout = html.Div([
    DashExcalidraw(id="canvas", height="600px"),
    html.Pre(id="count"),
])


@callback(Output("count", "children"), Input("canvas", "elements"))
def show(elements):
    return f"{len(elements or [])} elements on the canvas"


if __name__ == "__main__":
    app.run(debug=True)
```

Driving the canvas from Python is the same idea in reverse — write a `command`:

```python
import uuid
from dash import Input, Output, callback
from dash_excalidraw import DashExcalidraw


@callback(
    Output("canvas", "command"),
    Input("seed", "n_clicks"),
    prevent_initial_call=True,
)
def seed(_):
    return {
        # A NEW id every dispatch. The component dispatches once per unique
        # id, so re-sending the same one is a silent no-op.
        "id": str(uuid.uuid4()),
        "type": "updateScene",
        "payload": {
            "elements": [
                {"type": "rectangle", "x": 100, "y": 100,
                 "width": 200, "height": 120, "id": "r1"},
            ],
        },
    }
```

## Documentation

### 📚 **[excalidraw.2plot.dev](https://excalidraw.2plot.dev)**

Thirteen pages, each one a running Dash app you can draw on: basic usage, `initialData`,
theming, view modes, `UIOptions`, events, command dispatch, export, persistence, library,
collaboration, file uploads and AI scene generation.

Append `/llms.txt` to any page URL for the machine-readable Markdown of that page — the
whole site is built to be readable by agents as well as people.

To run the docs site locally:

```bash
pip install -r requirements.txt
# markdown2dash pins gunicorn<22, against the CVE-driven gunicorn>=23 floor in
# requirements.txt. pip cannot resolve both, so it installs without its
# dependency graph — every one of its real dependencies is already pinned there.
pip install --no-deps markdown2dash==0.1.2
python run.py
```

## The prop surface

38 props. Grouped by what they're for:

### Sizing and seeding

| Prop | Type | Notes |
|---|---|---|
| `width`, `height` | `str` | CSS values. `height` is the one you'll change. |
| `initialData` | `dict` | `{elements, appState, files, libraryItems, scrollToContent}`. **Mount-only** — see the gotcha below. |

### Output state — read-only from Python

Written by the component via `setProps` on every scene change.

| Prop | What it holds |
|---|---|
| `elements` | The current element array |
| `appState` | View background, zoom, scroll, grid/zen mode, theme, active tool |
| `files` | The binary-file map (`fileId → {dataURL, mimeType, …}`) |
| `serializedData` | The canonical Excalidraw JSON envelope, as a string |
| `externalizedSerializedData` | Same envelope with every inline `data:` URI stripped to `null` — **persist this one** |
| `sceneVersion` | Cheap change detector; compare instead of diffing `elements` |

### Editor configuration — declarative

`viewModeEnabled`, `zenModeEnabled`, `gridModeEnabled`, `isCollaborating`, `theme`
(`"light"`/`"dark"`), `name`, `langCode`, `libraryReturnUrl`, `detectScroll`,
`handleKeyboardGlobally`, `autoFocus`, `interceptLinkOpens`, `hideExcalidrawLinks`,
plus `UIOptions` and throttle controls (`pointerMoveThrottleMs`, `scrollThrottleMs`).

### Event snapshots

`lastPaste` · `lastPointerDown` · `lastPointerMove` · `lastPointerUp` ·
`lastScrollChange` · `lastLibraryChange` · `lastLinkOpen` · `lastFileAdded` ·
`lastExternalDrop` · `lastExport`

Each is a dict carrying a `timestamp`. `lastPointerMove` and `lastScrollChange` are
throttled — at 60 Hz they would otherwise be a callback storm.

### Commands

Twelve `command.type` values:

| Category | Types |
|---|---|
| Scene | `updateScene` · `resetScene` · `scrollToContent` |
| Files | `addFiles` · `replaceFiles` |
| Tools & UI | `setActiveTool` · `setToast` · `toggleSidebar` · `updateLibrary` |
| Export (async → `lastExport`) | `exportToSvg` · `exportToBlob` · `exportToCanvas` |

## Images at scale

Excalidraw stores every pasted or dropped image as a base64 `dataURL` inside the scene.
Leaving them inline bloats `serializedData` by orders of magnitude — a handful of
screenshots turns a 40 KB scene into a 12 MB one, and you pay that on every callback.

The wrapper supports the full upload-and-swap pattern:

1. **`lastFileAdded`** fires once per new inline file — `{fileId, mimeType, dataURL, size}`.
   Push the bytes to your storage layer from an ordinary callback.
2. **`command: replaceFiles`** with `{fileId: {dataURL: "https://…"}}` overwrites
   Excalidraw's copy in place. The old base64 string is unreferenced and garbage-collected.
3. **`externalizedSerializedData`** is the envelope with every remaining `data:` URI
   stripped. External URLs that step 2 installed survive. Persist this.

`dash_excalidraw.helpers` ships `decode_data_url`, `strip_inline_files` and
`restore_inline_files` — all pure Python, no dependencies.

**The component never makes the network call.** It emits the bytes and waits to be told
where they landed, which keeps the wrapper credential-free and backend-agnostic. Working
reference: [`/file-uploads`](https://excalidraw.2plot.dev/file-uploads).

## AI scene generation, and what it costs

The docs site's [`/ai-agent`](https://excalidraw.2plot.dev/ai-agent) page turns a
natural-language prompt into a scene by asking Claude or Gemini for Excalidraw JSON and
dispatching it with `command: updateScene`. The technique is the interesting part and it
generalizes: **the model returns data, not code**, so nothing it produces is executed —
a malformed response draws nothing, it cannot do anything.

Two costs worth stating plainly before you copy the pattern:

- **Tokens.** A scene of any complexity is a few thousand output tokens. The system prompt
  is stable across requests, so Claude calls use prompt caching — that is most of the
  saving. Costs are per-provider and change; check current pricing before wiring it to a
  public form.
- **Exposure.** An unauthenticated LLM endpoint on a public host is somebody else's free
  API credit. On the docs site that page ships behind an authentication tier so spend is
  bounded by sign-ups. If you deploy this pattern, put something in front of it.

The page runs the model call synchronously inside a Dash callback for clarity. For
production, move it to `background=True` or a task queue.

## Dash compatibility

| | |
|---|---|
| **Dash** | 3.0.3+ and the whole 4.x line |
| **Python** | 3.9+ |
| **React** | 18.3.1 (provided by Dash — not bundled) |
| **Excalidraw** | 0.18.1, pinned exactly and bundled |

The wheel depends on Dash and nothing else. The documentation site's requirements are
separate and never reach a `pip install dash-excalidraw`.

## Excalidraw 0.18 notes

Upgraded from 0.17.6. Two changes are worth knowing if you used the earlier release:

**`commitToHistory` became `captureUpdate`, and the default's meaning changed.** 0.17 left
undo history untouched when you passed nothing. 0.18 defaults to `EVENTUALLY`, which folds
a programmatic scene push into the *next* captured action — so a user's first Ctrl+Z after
your `updateScene` would also roll back their own previous edit. Nothing errors and nothing
warns. **This wrapper defaults to `IMMEDIATELY`**, so a Python-dispatched push is one
discrete, individually undoable step. Override per dispatch with
`payload["captureUpdate"] = "IMMEDIATELY" | "NEVER" | "EVENTUALLY"`; peer-driven scenes in a
collaborative app want `"NEVER"`. A legacy `commitToHistory` is translated and warned about
once.

**`collaborators` moved to top-level `SceneData`.** Either spelling is accepted from Python
and normalised.

0.18 also brings elbow arrows, flowchart shortcuts (Cmd+Arrow), scene search, image
cropping, element linking and the command palette.

## Common gotchas

- **`initialData` is mount-only.** Excalidraw owns the scene after mount. Setting the prop
  from a callback does nothing — use `command: updateScene` or `resetScene`.
- **Commands need unique ids.** Dispatching the same `{id, type}` twice is a no-op by
  design. Use `uuid.uuid4()`.
- **`lastExport` carries the id you dispatched.** Don't assume the newest `lastExport`
  answers your newest command; async exports arrive out of order.
- **`validateEmbeddable` takes glob strings**, not regex — `"*.youtube.com"`.

## Development

```bash
# Python side
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

# JS side (only needed when changing src/ts)
nvm use                 # .nvmrc pins node 20.11.1
npm install
npm run build           # webpack bundle + regenerated Python wrappers
npm run watch           # webpack --watch during iteration

# Test
pytest tests -q
```

The built bundle `dash_excalidraw/dash_excalidraw.js` is **committed on purpose**: the
release workflow gates on its commit timestamp, and tracking it keeps `pip install git+…`
working without a Node toolchain. Rebuild and commit it only in release-prep commits.

See [`REBUILD.md`](./REBUILD.md) for the architecture and the reasoning behind the prop
surface.

## Community & support

- **Discord** — [join](https://discord.gg/WEnZR35mrK)
- **YouTube** — [@2plotai](https://www.youtube.com/channel/UC6Bmo0t0ZUpU_xKBYW0bJuQ)
- **Issues** — [GitHub](https://github.com/pip-install-python/dash-excalidraw/issues)

## More from Pip Install Python LLC

Part of the [2plot network](https://2plot.dev) — component documentation sites, each one a
running Dash app: [leaflet](https://leaflet.2plot.dev) ·
[email](https://email.2plot.dev) · [flexlayout](https://flexlayout.2plot.dev) ·
[llms](https://llms.2plot.dev) · [boilerplate](https://boilerplate.2plot.dev)

## License

MIT — see [LICENSE](LICENSE).

Excalidraw itself is MIT-licensed by the Excalidraw team. Third-party notices for
everything bundled into the JavaScript artifact ship alongside it in
`dash_excalidraw/dash_excalidraw.js.LICENSE.txt`.
