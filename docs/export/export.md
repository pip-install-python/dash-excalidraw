---
name: Export round-trip
description: Export to SVG, PNG blob or canvas through an async command/lastExport round-trip correlated by id.
endpoint: /export
package: dash_excalidraw
category: Data flow
icon: mdi:export-variant
---

.. llms_copy::Export round-trip

.. toc::

### Overview

Excalidraw's export utilities are async. The wrapper models the round-trip as
(1) Python writes `command`, (2) JS awaits the export and writes `lastExport`
with the same id, (3) Python reads the result.

### Live demo

.. exec::docs.export.export
    :code: false

### Source

.. source::docs/export/export.py
    :defaultExpanded: false
    :withExpandedButton: true
