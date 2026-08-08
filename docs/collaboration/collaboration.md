---
name: Collaboration
description: Drive the collaborator UI and live cursors from Python — the wrapper exposes the knobs, you bring the transport.
endpoint: /collaboration
package: dash_excalidraw
category: Advanced
icon: mdi:account-group-outline
---

.. llms_copy::Collaboration

.. toc::

### Overview

The wrapper does not ship a transport layer, but it exposes the knobs:
`isCollaborating` toggles the collaborator UI, and `appState.collaborators`
can be driven via the updateScene command.

### Live demo

.. exec::docs.collaboration.collaboration
    :code: false

### Source

.. source::docs/collaboration/collaboration.py
    :defaultExpanded: false
    :withExpandedButton: true
