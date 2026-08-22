---
name: Persistence
description: Stream serializedData to a Store or a database and restore a scene later via updateScene.
endpoint: /persistence
package: dash_excalidraw
category: Data flow
icon: mdi:content-save-outline
lastmod: 2026-08-08
---

.. llms_copy::Persistence

.. toc::

### Overview

`serializedData` gives you the canonical Excalidraw envelope on every change —
stream it to a dcc.Store, write it back to a DB, restore it via `command` with
type='updateScene'.

### Live demo

.. exec::docs.persistence.persistence
    :code: false

### Source

.. source::docs/persistence/persistence.py
    :defaultExpanded: false
    :withExpandedButton: true
