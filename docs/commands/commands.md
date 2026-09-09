---
name: Command dispatch
description: Call Excalidraw's imperative API from Python through a JSON-safe command prop dispatched once per id.
endpoint: /commands
package: dash_excalidraw
category: Data flow
order: 3
icon: mdi:console-line
lastmod: 2026-09-08
---

.. llms_copy::Command dispatch

.. toc::

### Overview

Every imperative API the upstream Excalidraw exposes is callable from Python
as a `command` prop: a dict with `id`, `type`, and `payload`. The component
dispatches once per unique id, then clears the prop so React re-renders don't
re-fire.

### The twelve command types

| `type` | Payload | Notes |
|:-------|:--------|:------|
| `updateScene` | `{elements?, appState?, collaborators?, captureUpdate?}` | See history, below |
| `addFiles` | A **list** of `{id, mimeType, dataURL, created}` | Raw passthrough |
| `replaceFiles` | A **map** `{fileId: {dataURL, mimeType?}}` | Overwrites in place |
| `resetScene` | `{}` | |
| `scrollToContent` | `{target?, opts?}` | |
| `setActiveTool` | `{type: "selection"}`, `{type: "rectangle"}`, … | Defaults to `selection` |
| `setToast` | `{message, duration?}`, or `None` to clear | |
| `toggleSidebar` | `{name, force?}` | |
| `updateLibrary` | `{libraryItems, merge?}` | |
| `exportToSvg` | Export options | Replies on `lastExport` |
| `exportToBlob` | Export options, `{mimeType?}` | Replies on `lastExport` |
| `exportToCanvas` | Export options, `{mimeType?}` | Replies on `lastExport` |

`addFiles` and `replaceFiles` both end at Excalidraw's `addFiles`, but they
are not interchangeable. Use `replaceFiles` to swap an existing file's bytes
— it takes the id-keyed map, fills `created` and `mimeType` for you, and
skips malformed entries; that is the shape [File uploads](/file-uploads)
uses to trade base64 for URLs. Use `addFiles` only when you need the raw
Excalidraw `BinaryFileData` list, including fields `replaceFiles` would
drop; you must supply `created` yourself, and a malformed entry is a silent
no-op.

### Scene pushes and undo history

Excalidraw `0.18` replaced `commitToHistory` with `captureUpdate`, **and
changed what the default means**. `0.17` left undo history untouched when no
flag was given; `0.18` defaults to folding a programmatic push into the
*next* captured action, so a user's first Ctrl+Z after your `updateScene`
would also roll back their own previous edit. Nothing errors and nothing
warns.

This wrapper therefore defaults `captureUpdate` to `IMMEDIATELY`: a
dispatched scene push is a deliberate edit and undoes as one discrete step.
Override it per command:

```python
{
    "id": str(uuid.uuid4()),
    "type": "updateScene",
    "payload": {
        "elements": elements,
        "captureUpdate": "NEVER",   # or "IMMEDIATELY" (default), "EVENTUALLY"
    },
}
```

| `captureUpdate` | Effect on undo history |
|:----------------|:-----------------------|
| `IMMEDIATELY` | *(default)* The push is its own undo step |
| `NEVER` | The push is not recorded; Ctrl+Z skips past it |
| `EVENTUALLY` | Folded into the next captured action — Excalidraw's own `0.18` default |

Two guardrails worth knowing. Passing the removed `commitToHistory` still
works: it is translated (`True` → `IMMEDIATELY`, `False` → `NEVER`) and logs
a one-time console warning telling you to switch. And an unrecognised
`captureUpdate` value is **not** accepted silently — it warns and falls back
to `IMMEDIATELY`, because a typo that looked like it took effect is the
worse failure.

### Live demo

.. exec::docs.commands.commands
    :code: false

### Source

.. source::docs/commands/commands.py
    :defaultExpanded: false
    :withExpandedButton: true
