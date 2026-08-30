---
name: initialData
description: Pre-populate the canvas on mount with elements, appState overrides and library items.
endpoint: /initial-data
package: dash_excalidraw
category: Getting started
order: 2
icon: mdi:database-import-outline
lastmod: 2026-08-08
---

.. llms_copy::initialData

.. toc::

### Overview

Pre-populate the canvas with elements, appState overrides, and optionally
library items. The prop is consumed once on mount — after that, drive changes
through the command dispatch.

### Live demo

.. exec::docs.initial-data.initial_data
    :code: false

### Source

.. source::docs/initial-data/initial_data.py
    :defaultExpanded: false
    :withExpandedButton: true
