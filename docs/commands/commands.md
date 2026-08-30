---
name: Command dispatch
description: Call Excalidraw's imperative API from Python through a JSON-safe command prop dispatched once per id.
endpoint: /commands
package: dash_excalidraw
category: Data flow
order: 3
icon: mdi:console-line
lastmod: 2026-08-08
---

.. llms_copy::Command dispatch

.. toc::

### Overview

Every imperative API the upstream Excalidraw exposes is callable from Python
as a `command` prop: a dict with `id`, `type`, and `payload`. The component
dispatches once per unique id, then clears the prop so React re-renders don't
re-fire.

### Live demo

.. exec::docs.commands.commands
    :code: false

### Source

.. source::docs/commands/commands.py
    :defaultExpanded: false
    :withExpandedButton: true
