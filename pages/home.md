# dash-excalidraw — Excalidraw drawing canvas for Dash

> **`dash-excalidraw` — the [Excalidraw](https://excalidraw.com/) whiteboard as a first-class [Dash](https://dash.plotly.com/) component.** By [Pip Install Python](https://2plot.dev).

Every canvas on this site is a running Dash app. Draw on them.

```bash
pip install dash-excalidraw
```

---

## The problem this solves

Excalidraw is a React application with a large imperative API. Wrapping it for Dash
means answering one question honestly: **what can cross the Python/JavaScript bridge?**

Only JSON can. Functions, RegExps and class instances cannot. Most wrappers stop
there and hand you a `clientside_callback` for anything interesting — which means
writing JavaScript to use a Python component.

This one translates the entire surface into three JSON-safe patterns, so you write
ordinary `@callback`s and never touch JavaScript.

| Upstream shape | What Python sees | Why |
|---|---|---|
| Callbacks (`onPaste`, `onPointerUpdate`, …) | **Snapshot props** — `lastPaste`, `lastPointerMove`, … each with a `timestamp` | A callback can't be serialized; a record of it firing can. The timestamp is how you dedupe. |
| Imperative methods (`updateScene`, `exportToSvg`, …) | **`command`** — `{id, type, payload}`, dispatched once per unique `id` | One prop covers twelve methods, and a re-render can't re-fire a command. |
| Async results | **`lastExport`**, carrying the `id` you dispatched | Exports resolve out of order under load. The id is how you correlate. |
| `validateEmbeddable` RegExp | A **list of glob strings**, compiled to RegExps on the JS side | A RegExp has no JSON form. `"*.youtube.com"` does. |

---

## Thirty seconds to a canvas

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

Nothing else is required. The Excalidraw bundle, its stylesheet and its UI font ship
inside the wheel as one self-contained JavaScript file — no CDN dependency at load
time, no `external_stylesheets` entry, no build step.

---

## Where to go next

**Start here** — [Basic usage](/basic) is the smallest useful app.
[initialData](/initial-data) seeds a scene at mount.

**Reading the canvas** — [Events](/events) shows every callback as a snapshot prop.
[Persistence](/persistence) streams `serializedData` to a store and restores it.

**Driving the canvas** — [Command dispatch](/commands) is the imperative API from
Python. [Export](/export) is the async round-trip. [Library](/library) reads and
writes the shape library.

**Appearance** — [Theming](/theming), [View modes](/view-modes), [UIOptions](/ui-options).

**At scale** — [File uploads](/file-uploads) keeps canvas JSON small by pushing
pasted images to storage and swapping the base64 for URLs.
[Collaboration](/collaboration) drives the collaborator UI and live cursors.

**AI** — [AI agent](/ai-agent) turns a natural-language prompt into a scene, and is
honest about what that costs.

---

## Excalidraw 0.18

Pinned exactly at 0.18.1, which brings elbow arrows, flowchart shortcuts, scene
search, image cropping, element linking and the command palette — and patches the
mermaid XSS advisory.

One upgrade note worth reading before you dispatch a scene from Python: 0.18 replaced
`commitToHistory` with `captureUpdate`, and **changed what the default means**. 0.17
left undo history untouched; 0.18 folds a programmatic push into the *next* captured
action, so a user's first Ctrl+Z after your `updateScene` would also roll back their
own previous edit. Nothing errors and nothing warns.

This wrapper defaults to `IMMEDIATELY`, so a Python-dispatched push is one discrete,
individually undoable step. [Command dispatch](/commands) covers the override.

---

## For agents

Append `/llms.txt` to any URL on this site for the machine-readable Markdown of that
page. The index is at [/llms.txt](/llms.txt), and every page document opens with a
navigation block back to the site and network indexes rather than being a dead end.
