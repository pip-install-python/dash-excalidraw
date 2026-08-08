---
name: Events
description: Every Excalidraw callback surfaced as a timestamped snapshot prop you can read from a Dash callback.
endpoint: /events
package: dash_excalidraw
category: Data flow
icon: mdi:flash-outline
---

.. llms_copy::Events

.. toc::

### Overview

Every Excalidraw callback is surfaced as a setProps-written snapshot prop on
the Python side. Interact with the canvas and watch the panels update.

### Live demo

.. exec::docs.events.events
    :code: false

### Source

.. source::docs/events/events.py
    :defaultExpanded: false
    :withExpandedButton: true
