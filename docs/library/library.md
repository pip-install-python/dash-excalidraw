---
name: Library
description: Read and write the Excalidraw shape library from Python with lastLibraryChange and updateLibrary.
endpoint: /library
package: dash_excalidraw
category: Advanced
order: 1
icon: mdi:bookshelf
lastmod: 2026-08-08
---

.. llms_copy::Library

.. toc::

### Overview

The library menu holds reusable shapes. `lastLibraryChange` fires whenever the
user adds/removes an item; `command: updateLibrary` lets you push items in
from Python.

### Live demo

.. exec::docs.library.library
    :code: false

### Source

.. source::docs/library/library.py
    :defaultExpanded: false
    :withExpandedButton: true
