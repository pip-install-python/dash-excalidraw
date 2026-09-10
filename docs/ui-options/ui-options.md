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

`hideExcalidrawLinks` defaults to `True` and works in **both directions** —
set it to `False` and the links come back, no reload needed. It injects one
stylesheet rather than patching the menu, so it survives Excalidraw
re-rendering its chrome.

That stylesheet is shared by every canvas on the page and reference counted:
it goes in for the first canvas that wants the links hidden and comes out only
when the last one stops wanting that. On a single-canvas page the switch is
simply symmetric. On a page with several, a canvas turning the links back on
while another still hides them will appear to do nothing — the neighbour's
preference wins, which is the only behaviour that stops one component changing
another's chrome. [Coverage](/coverage) has the multi-canvas detail.

### Live demo

.. exec::docs.ui-options.ui_options
    :code: false

### Source

.. source::docs/ui-options/ui_options.py
    :defaultExpanded: false
    :withExpandedButton: true
