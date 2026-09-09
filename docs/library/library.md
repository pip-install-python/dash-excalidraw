---
name: Library
description: Read and write the Excalidraw shape library from Python with lastLibraryChange and updateLibrary.
endpoint: /library
package: dash_excalidraw
category: Advanced
order: 1
icon: mdi:bookshelf
lastmod: 2026-09-08
---

.. llms_copy::Library

.. toc::

### Overview

The library menu holds reusable shapes. `lastLibraryChange` fires whenever the
user adds/removes an item; `command: updateLibrary` lets you push items in
from Python.

### Coming back from the public library

The sidebar's **Browse Library** button sends the user to Excalidraw's
public library site. `libraryReturnUrl` is the URL that site sends them back
to once they pick a shape:

```python
DashExcalidraw(
    id="canvas",
    libraryReturnUrl="https://your-app.example.com/drawing",
)
```

It has no default of its own. Left unset, the return trip is whatever
Excalidraw decides, which is not a URL your app chose — so set it to the
page hosting the canvas whenever the library button is reachable, and the
user comes back to you rather than wherever the fallback points.

### Live demo

.. exec::docs.library.library
    :code: false

### Source

.. source::docs/library/library.py
    :defaultExpanded: false
    :withExpandedButton: true
