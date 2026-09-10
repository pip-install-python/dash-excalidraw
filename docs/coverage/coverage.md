---
name: Coverage
description: The three commands and ten props no other example reaches — the leftovers of the prop surface, in one runnable place.
endpoint: /coverage
package: dash_excalidraw
category: Advanced
order: 6
icon: mdi:checkbox-multiple-marked-outline
lastmod: 2026-09-09
---

.. llms_copy::Coverage

.. toc::

### Why this page exists

Every other page here demonstrates a feature. This one covers the leftovers.

The component ships 38 props and 12 command types. Sweeping every example
module for the commands it dispatches — both the `{"type": "X"}` dict form and
the `_cmd("X", …)` helper form — and for every prop reached either as a
constructor keyword or through an `Input`/`Output`/`State`, three commands and
ten props came back untouched. A reader could find them in the component
reference and nowhere else.

That is the gap this page closes. It is not a tutorial; it is the part of the
surface that would otherwise be documented only as a table row.

### The three commands

| `type` | What it does here | How you see it |
|:-------|:------------------|:---------------|
| `addFiles` | Registers one 1×1 PNG as raw `BinaryFileData` | The readout's *registered file ids* grows |
| `exportToCanvas` | Exports the scene through a canvas element | The preview appears, tagged with the dispatched `id` |
| `updateLibrary` | Merges a two-rectangle item into the library | The library panel opens with the item in it |

`addFiles` registers **bytes**, not a visible element. Excalidraw draws an
image only when a scene element references the file id, so the file appearing
in the readout while the canvas stays empty is correct, not a failure — see
[File uploads](/file-uploads) for the flow that pairs the two.

`exportToCanvas` returns a `data:` URL, where `exportToSvg` returns markup.
Both land on `lastExport` carrying the id you dispatched, which is what lets
you tell two in-flight exports apart. [Export round-trip](/export) covers the
correlation.

### The ten props

| Prop | Default | What it does | Live? |
|:-----|:--------|:-------------|:------|
| `langCode` | `"en"` | Excalidraw's UI language | Yes |
| `name` | *(unset)* | Scene name, used by the export dialog | Yes |
| `width` | `"100%"` | CSS width of the container | Yes |
| `detectScroll` | `True` | Canvas handles wheel events | Yes |
| `handleKeyboardGlobally` | `True` | Key handling on `document`, not the canvas | Yes |
| `hideExcalidrawLinks` | `True` | Hides the GitHub/Discord/X menu group | **One-way — see below** |
| `autoFocus` | `True` | Focus the canvas on mount | Mount only |
| `libraryReturnUrl` | *(unset)* | Where the Browse Library trip returns to | Mount only, in effect |
| `appState` | — | Full serializable app state | Read-only |
| `sceneVersion` | — | Monotonic scene counter | Read-only |

`autoFocus` is read by Excalidraw when the canvas mounts. A switch for it
would be theatre — this page sets it to `False` and that takes effect on page
load, nowhere else. Reload to change it.

`appState` and `sceneVersion` are written *out* by the component. Setting
them from Python does nothing; the readout on the right is what they are for.
`sceneVersion` is a single integer and far cheaper to compare than diffing
`elements`, which is the reason it exists.

### How the links switch behaves with more than one canvas

`hideExcalidrawLinks` works in both directions — switch it off and the links
come back, without a reload.

It is worth knowing how, because the mechanism shows through when a page has
more than one canvas. It is a single stylesheet shared by every canvas, and it
is reference counted: installed for the first canvas that asks for it, removed
only when the LAST canvas that wanted it stops. So one canvas turning the
links back on cannot unhide them under its neighbours — you will see the
switch flip with nothing changing, and that is correct. Unmounting counts as
letting go, so a canvas that disappears no longer leaves the stylesheet behind.

This used to be one-way: the sheet went in and never came out, and nothing in
the API said so. R5 fixed it; the page you are reading described the old
behaviour until then.

### Live demo

.. exec::docs.coverage.coverage
    :code: false

### Source

.. source::docs/coverage/coverage.py
    :defaultExpanded: false
    :withExpandedButton: true
