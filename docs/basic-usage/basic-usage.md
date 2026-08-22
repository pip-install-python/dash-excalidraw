---
name: Basic usage
description: The minimum viable DashExcalidraw — one component, default props, a working canvas.
endpoint: /basic
package: dash_excalidraw
category: Getting started
icon: mdi:draw
lastmod: 2026-08-08
---

.. llms_copy::Basic usage

.. toc::

### Overview

The smallest useful app is one component with default props. Draw on the canvas
below — zoom, pan, undo, the shape tools, the library and the context menu all
work with no configuration at all.

That is the point of this page: **nothing on it is set up.** Everything you can
do to the canvas is Excalidraw's own behaviour, reaching Dash unmodified.

### What you get for free

Mounting `DashExcalidraw` with nothing but an `id` gives you the full editor:

- **Every drawing tool** — rectangle, diamond, ellipse, arrow, line, freedraw,
  text, image, eraser and the frame tool, with keyboard shortcuts (`1`–`9`).
- **The shape library**, including anything the user has saved locally.
- **Undo and redo**, scoped to this canvas.
- **Zoom and pan**, including scroll-to-zoom and space-drag.
- **The context menu**, with copy/paste styles, grouping, layering and locking.
- **Excalidraw 0.18's additions** — elbow arrows, flowchart shortcuts
  (`Cmd`/`Ctrl` + arrow key), scene search, image cropping, element linking and
  the command palette.

None of that costs you a callback.

### The minimum app

```python
from dash import Dash
from dash_excalidraw import DashExcalidraw

app = Dash(__name__)
app.layout = DashExcalidraw(id="canvas", height="600px")

if __name__ == "__main__":
    app.run(debug=True)
```

`height` is the prop you will actually change. Excalidraw fills its parent, so a
canvas that looks too short is almost always a container-height problem rather
than a component one.

### Live demo

.. exec::docs.basic-usage.basic
    :code: false

### Reading what the user drew

The component writes its state back through ordinary props, so a callback reads
the canvas the same way it reads a dropdown:

```python
from dash import Input, Output, callback

@callback(Output("count", "children"), Input("canvas", "elements"))
def show(elements):
    return f"{len(elements or [])} elements"
```

`elements` updates on every scene change. If you only need to know *that*
something changed — not what — read `sceneVersion` instead; it is a single
integer and far cheaper to compare than diffing the element array.

### Where to go next

- [initialData](/initial-data) — seed the canvas at mount.
- [Events](/events) — every Excalidraw callback, as a snapshot prop.
- [Command dispatch](/commands) — drive the canvas from Python.
- [Persistence](/persistence) — save a scene and restore it later.

### Source

.. source::docs/basic-usage/basic.py
    :defaultExpanded: false
    :withExpandedButton: true

### Component reference

Every prop on the component, generated from the TypeScript source.

.. kwargs::DashExcalidraw
