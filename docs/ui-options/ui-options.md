---
name: UIOptions
description: "The JSON-safe subset of Excalidraw's UIOptions: hide toolbar actions, tools and the welcome screen."
endpoint: /ui-options
package: dash_excalidraw
category: Appearance
order: 3
icon: mdi:tune-variant
lastmod: 2026-09-09
---

.. llms_copy::UIOptions

.. toc::

### The welcome screen is a prop, and it is reactive

`UIOptions.welcomeScreen` is read **once**, while the canvas mounts. A control
bound to it appears to do nothing, because by the time you click it Excalidraw
has stopped looking. The overlay's real state is `appState.showWelcomeScreen`,
so the component takes a top-level prop and pushes it there:

```python
DashExcalidraw(
    id="canvas",
    welcomeScreen=True,
    welcomeScreenContent={
        "title": "dash-excalidraw",
        "subtitle": "Draw something, or load a scene from Python.",
    },
)
```

`welcomeScreen` toggles live — it brings the overlay back after you have drawn
and dismissed it. `welcomeScreenContent` replaces the wording; the menu hints
stay Excalidraw's own, so they cannot fall out of step with the menu they
describe.

To open on a scene rather than a blank canvas, pass `welcomeScene` — any
`{elements, appState, files}` object, which is the shape `initialData` and
`externalizedSerializedData` both use. [/trace-image](/trace-image) will hand
you one as copyable JSON. It is mount-only, like `initialData`: Excalidraw
owns the scene once it has one.

### Overview

The JSON-safe subset of Excalidraw's UIOptions prop. Toggle the switches below
and watch the canvas chrome change.

### The Excalidraw links menu

One piece of chrome is not part of `UIOptions` and has its own prop.
Excalidraw's hamburger menu carries a link group pointing at its own GitHub,
Discord and X accounts. In a product embedding the canvas those send users
off your app, so this wrapper hides them by default:

```python
DashExcalidraw(id="canvas", hideExcalidrawLinks=False)  # show them again
```

`hideExcalidrawLinks` defaults to `True` and works in **both directions** —
set it to `False` and the links come back, no reload. Each canvas decides for
itself, so two on one page may disagree.

It is a render condition, not a stylesheet: the wrapper composes its own main
menu, mirroring Excalidraw's default item for item, and simply omits the
vendor's links group when you ask it to. That is the only supported way to
reach that group — no `UIOptions` key does.

Alongside it, `docsLinkUrl` puts one item of the wrapper's own in the menu,
independently of the switch above:

```python
DashExcalidraw(
    id="canvas",
    hideExcalidrawLinks=False,          # show Excalidraw's GitHub / X / Discord
    docsLinkUrl="https://my-app.example.com/help",
    docsLinkLabel="Drawing help",       # relabel whenever you re-point the URL
)
```

| State | Vendor links group | Our docs item |
|:------|:-------------------|:--------------|
| Default | hidden | shown |
| `hideExcalidrawLinks=False` | shown | shown |
| `docsLinkUrl=""` | hidden | none |

Set `docsLinkUrl=""` to render no item of ours at all. And relabel when you
re-point: a menu entry that names one destination and opens another is the
reason this is a pair of props rather than one. [Coverage](/coverage) covers
the composition, the two `UIOptions` gates it replicates, and what still
points at Excalidraw (the Help dialog and two error dialogs — deliberately).

The three canvases below are the three states, side by side. Open the
hamburger menu on each.

### Live demo

.. exec::docs.ui-options.ui_options
    :code: false

### Source

.. source::docs/ui-options/ui_options.py
    :defaultExpanded: false
    :withExpandedButton: true
