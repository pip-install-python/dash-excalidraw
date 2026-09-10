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
| `hideExcalidrawLinks` | `True` | Hides the vendor's links group | Yes |
| `docsLinkUrl` | `"https://excalidraw.2plot.dev"` | Our own menu item's URL; `""` renders none | Yes |
| `docsLinkLabel` | `"dash-excalidraw docs"` | That item's visible label | Yes |
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

### The main menu is composed here, not by Excalidraw

The wrapper renders its own `MainMenu` rather than letting Excalidraw render
the default one. It mirrors the vendor's `DefaultMainMenu` item for item and
in the same order — Load scene, Save to file, Export, Save as image, Find,
Help, Reset canvas, then the links, then Theme and Canvas background.

It does that because there is no other supported way to control the links
group: the vendor's `Socials` item is composed at a single site inside
Excalidraw and no `UIOptions` key reaches it. Two consequences worth knowing:

- **Each canvas decides for itself.** `hideExcalidrawLinks` is a render
  condition on this canvas's own menu, so it works in both directions and two
  canvases on one page can disagree. It was one-way until R5 — a shared
  stylesheet that went in and never came out — and this page said so.
- **Two switches are ours to keep in step.** Most default items decide their
  own visibility, but `Export` and `Save as image` are gated by Excalidraw
  where the menu is composed. Composing our own means replicating exactly
  those two, so `UIOptions.canvasActions.export` and `.saveAsImage` still
  work. A test in the JS harness reads the vendor's own composition and fails
  if a version bump changes the item set, rather than letting our copy quietly
  become a copy of an older menu.

| State | Vendor links group | Our docs item |
|:------|:-------------------|:--------------|
| Default | hidden | shown |
| `hideExcalidrawLinks=False` | shown | shown |
| `docsLinkUrl=""` | hidden | none |

`docsLinkLabel` exists so that re-pointing the URL does not leave a menu entry
naming one destination and opening another. If you send `docsLinkUrl` to your
own site, relabel it.

### What still points at Excalidraw

Being honest about the residue: the menu is not the only place the vendor
links out, and the rest is deliberately left alone.

- **The Help dialog** links to `docs.excalidraw.com`, `plus.excalidraw.com/blog`,
  the Excalidraw GitHub issues tracker and their YouTube channel.
- **Two error dialogs** link to the vendor's FAQ and to "open an issue".

That is Excalidraw's manual for Excalidraw's canvas, and a wrapper that
rewrote it would be sending people to the wrong project for help with the
thing that is actually failing. Out of scope on purpose.

### Live demo

.. exec::docs.coverage.coverage
    :code: false

### Source

.. source::docs/coverage/coverage.py
    :defaultExpanded: false
    :withExpandedButton: true
