---
name: Migrating from 0.0.x
description: What changed between the PyPI 0.0.x releases and the current build — no prop was removed or renamed, but three defaults did change.
endpoint: /migration
package: dash_excalidraw
category: Getting started
order: 3
icon: mdi:swap-horizontal
lastmod: 2026-09-08
---

.. llms_copy::Migrating from 0.0.x

.. toc::

### The short version

This page covers the upgrade from the `0.0.x` series to dash-excalidraw
{{VERSION:dash-excalidraw}}, the build this site runs on.

**No prop was removed. No prop was renamed.** All 21 props that `0.0.4`
exposed are still present and still spelled the same way — the current
surface is a strict superset of the released one. Read against the shipped
`_prop_names` of every published wheel (`0.0.1`, `0.0.2`, `0.0.3`, `0.0.4`),
not against release notes.

**Three defaults changed.** That is the entire breaking surface, and it is
the part a compatibility shim could not have helped with anyway. If your app
sets these three props explicitly, the upgrade is a version bump and nothing
else.

### The three defaults

| Prop | `0.0.x` default | Current default | Keep the old behaviour with |
|:-----|:----------------|:----------------|:----------------------------|
| `isCollaborating` | `True` | `False` | `isCollaborating=True` |
| `height` | `"400px"` | `"600px"` | `height="400px"` |
| `langCode` | *(unset)* | `"en"` | `langCode=None` |

`isCollaborating` is the one most likely to be visible: it drives the
collaborator UI, so a canvas that used to show it now does not. `height` is
the one most likely to be *invisible* in a review and obvious in production
— every canvas grows by 200px unless a stylesheet was already overriding it.

For the avoidance of doubt, `gridModeEnabled` did **not** change. It
defaulted to `False` in `0.0.4` and it defaults to `False` now. Some
migration notes claim otherwise.

```python
# The upgrade, stated as a diff, for an app that relied on 0.0.x defaults.
DashExcalidraw(
    id="canvas",
    isCollaborating=True,   # was the default; now opt in
    height="400px",         # was the default; now 600px
    langCode=None,          # was unset; now "en"
)
```

### What was added

Seventeen props are new since `0.0.4`. Nothing you already wrote needs to
change to accommodate them — they are additive.

- **Command dispatch.** `command` accepts `{id, type, payload}` and covers
  twelve imperative Excalidraw methods. See [Command dispatch](/commands).
- **Event snapshots.** `lastPointerDown`, `lastPointerUp`, `lastPointerMove`,
  `lastScrollChange`, `lastPaste`, `lastLibraryChange`, `lastLinkOpen`,
  `lastExport`, `lastFileAdded` and `lastExternalDrop` — every Excalidraw
  callback surfaced as a timestamped prop. See [Events](/events).
- **Persistence.** `externalizedSerializedData` and `sceneVersion`. See
  [Persistence](/persistence) and [File uploads](/file-uploads).
- **Behaviour switches.** `interceptLinkOpens`, `hideExcalidrawLinks`,
  `pointerMoveThrottleMs`, `scrollThrottleMs`.

### Props that never existed

A migration table circulating elsewhere lists `onPaste`, `onPointerUpdate`,
`onScrollChange`, `onLibraryChange`, `onLinkOpen`, `excalidrawAPI`,
`renderTopRightUI`, `renderCustomStats`, `renderEmbeddable` and
`generateIdForFile` as things to migrate away from.

**None of them was ever a Dash prop in any published release.** They are
names from Excalidraw's underlying React API. What the wheels actually
exposed was `0.0.1` with six props, and `0.0.2` through `0.0.4` with the
same twenty-one. If your `0.0.x` code passes any of those names, Dash was
already ignoring it, and removing it changes nothing.

This matters because it changes what you look for. There is no callback to
port and no `excalidrawAPI` handle to replace — those patterns were never
available from Python. What you are adopting is new capability, not a
replacement for something you lost.

### There is no compatibility shim

Deliberately, and not for lack of effort.

A shim exists to keep old names working. Since no name changed, there is
nothing for one to translate. The only thing a shim could do here is pin the
three old defaults — which would mean shipping a component whose behaviour
depends on which import you used, and freezing the defaults the rebuild
exists to correct.

Set the three props explicitly instead. It is three lines, it is greppable,
and it leaves your app saying what it means.

### Version pinning

`0.0.x` and the current release are not API-compatible in the defaults
described above, so pin deliberately rather than by accident. Pin at or
above the version named at the top of this page — that number is read from
the installed distribution, so it is the one this documentation was built
against.

If you need to stay on the old series while you migrate, pin
`dash-excalidraw==0.0.4` and upgrade once the three lines above are in
place.
