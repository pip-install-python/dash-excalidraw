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

### One thing that does not turn off again

**`hideExcalidrawLinks` is one-way within a page load.** Switching it on
injects a stylesheet; switching it back off does not remove it, so the links
stay hidden until you reload.

That is deliberate in the sense that the stylesheet is shared by every canvas
on the page — removing it for one component would unhide the links under all
of them — but the effect is that the prop is not symmetric, and nothing in the
API says so. Set it once at mount and treat it as fixed; if you need the links
back, reload with `hideExcalidrawLinks=False`.

The switch below is left live rather than disabled, because watching it fail
to reverse is a more useful thing to know than being prevented from trying.

### Live demo

.. exec::docs.coverage.coverage
    :code: false

### Source

.. source::docs/coverage/coverage.py
    :defaultExpanded: false
    :withExpandedButton: true
