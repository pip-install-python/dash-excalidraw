---
name: UIOptions
description: "The JSON-safe subset of Excalidraw's UIOptions: hide toolbar actions, tools and the welcome screen."
endpoint: /ui-options
package: dash_excalidraw
category: Appearance
order: 3
icon: mdi:tune-variant
lastmod: 2026-09-08
---

.. llms_copy::UIOptions

.. toc::

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

`hideExcalidrawLinks` defaults to `True`. It works by injecting one
stylesheet — shared across every canvas on the page, injected once — rather
than by patching the menu, so it survives Excalidraw re-rendering its
chrome. Set it to `False` if you would rather credit the upstream project in
the UI; nothing else about the menu changes either way.

### Live demo

.. exec::docs.ui-options.ui_options
    :code: false

### Source

.. source::docs/ui-options/ui_options.py
    :defaultExpanded: false
    :withExpandedButton: true
