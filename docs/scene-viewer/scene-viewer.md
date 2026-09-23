---
name: Scene viewer
description: Paste or upload raw Excalidraw scene JSON — a trace, a .excalidraw file, a model's reply — and render it on a live canvas.
endpoint: /scene-viewer
package: dash_excalidraw
category: Advanced
order: 7
icon: mdi:code-json
lastmod: 2026-09-22
---

.. llms_copy::Scene viewer

.. toc::

### Overview

[Trace an image](/trace-image) hands its drawing back as **scene JSON**. This
page is the other half of that loop: paste scene JSON in, press **Render**, and
the canvas draws it. Edit the drawing, press **Canvas → JSON**, and the box
holds the edited scene, ready to copy out again.

No model is called, so nothing here spends anything, and the page works on
this site even though the AI pages cannot run here. A trace made on a local
checkout renders here the same way.

### What it accepts

| Paste this | Where it comes from |
|:-----------|:--------------------|
| `{"type": "excalidraw", "elements": [...], "appState": {...}, "files": {...}}` | `/trace-image`'s Scene JSON panel, `serializedData`, a `.excalidraw` file from excalidraw.com |
| `{"elements": [...], "appState": {...}}` | Anything shaped like [`initialData`](/initial-data) or `welcomeScene` |
| `[{...}, {...}]` | A bare element array |
| A model's raw reply | [AI agent](/ai-agent) output: a markdown code fence, a sentence before the object and trailing commas are all tolerated |
| `"{\"elements\": ...}"` | `serializedData` copied out of a `dcc.Store` or a log, which is a JSON *string* and arrives quoted once more than it should |

**Upload file** takes a `.json` or `.excalidraw` file and does the same thing.
A `.excalidrawlib` library file is refused with a pointer to
[Library](/library): it holds library items, not a scene.

### What Excalidraw would drop without saying so

Excalidraw's loader is forgiving, and the price is that it throws things away
without saying anything. An element of an unknown type, a `selection` element,
a zero-sized shape and a line with fewer than two points all vanish on load.
The drawing just comes out shorter. The page does the same checks in Python
first and says what it found, so a 30-element scene that draws 26 comes with
the reason for the missing four:

- **Skipped types.** The list of types that survive was read from the pinned
  Excalidraw 0.18 bundle's `restoreElement`, not remembered.
- **Invisibly small elements.** These mirror `isInvisiblySmallElement`.
- **Deleted elements.** `isDeleted: true` elements stay in the scene but are
  not drawn.
- **Duplicate ids.** Excalidraw gives each repeat a fresh random id, so an
  arrow bound to that id can end up attached to the other copy.
- **Images with no bytes.** A trace's JSON comes from
  `externalizedSerializedData`, which strips every inline `data:` URI to
  `null`. An image with no bytes draws as an empty placeholder. Serve the file
  and point the scene at a URL; [File uploads](/file-uploads) is that pattern.

Only `viewBackgroundColor`, `gridSize` and `gridStep` are applied from a pasted
`appState`. Theme, view mode, zen mode and grid mode are this component's
props, and a scene that set them would fight the props. Scroll and zoom are
worked out again when the page fits the scene to the canvas.

### How a render works: a command queue

`initialData` is **mount-only**. It gives the canvas its first scene (the
sample, here), and changing it afterwards does nothing. Every render after that
goes through [command dispatch](/commands), and one render takes four commands:

1. `resetScene` clears the elements, the undo history and the previous scene's
   background.
2. `updateScene` loads the scene with `captureUpdate: "NEVER"`, so the first
   Ctrl+Z does not undo the whole load and leave an empty canvas.
3. `replaceFiles` sends the image bytes, if there are any. It is not
   `addFiles`, because `addFiles` does nothing when the canvas already holds
   that id, and the second render of the same scene would keep the old image.
4. `scrollToContent` with `fitToContent` fits the drawing to the view. It
   zooms out to fit and never zooms in past 100%.

The canvas holds **one** `command` at a time. It runs the command and then sets
`command` back to `None`. You cannot return all four from one callback, because
each would overwrite the one before it ran. So the render callback sends the
first command and parks the rest in a `dcc.Store`. A second callback, fired by
`command` going back to `None`, sends the next one:

```python
@callback(Output("canvas", "command"),
          Output("queue", "data", allow_duplicate=True),
          Input("canvas", "command"),
          State("queue", "data"),
          prevent_initial_call=True)
def next_command(current, queue):
    if current is not None or not queue:  # busy, or nothing left
        return no_update, no_update
    head, *rest = queue
    return head, rest
```

You can reuse this for any sequence of commands whose order matters.

### Live demo

.. exec::docs.scene-viewer.scene_viewer
    :code: false

### Source

.. source::docs/scene-viewer/scene_viewer.py
    :defaultExpanded: false
    :withExpandedButton: true

.. source::lib/scene_json.py
    :defaultExpanded: false
    :withExpandedButton: true
