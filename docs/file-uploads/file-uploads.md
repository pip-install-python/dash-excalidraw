---
name: File uploads
description: "Keep canvas JSON small: push pasted images to external storage and swap the base64 for URLs."
endpoint: /file-uploads
package: dash_excalidraw
category: Advanced
order: 2
icon: mdi:cloud-upload-outline
lastmod: 2026-08-08
---

.. llms_copy::File uploads

.. toc::

### Where the bytes go, and how to point that at a CDN

A dropped file arrives as **base64** — that is how the browser hands it over,
and it is the wrong place for it to stay. Inline in the scene, a 120 KB image
is ~160 KB of base64 inside every `serializedData` you persist, every callback
payload that carries the scene, and every undo step. The job of this page is
getting it out.

The path is four steps, and only the third is deployment-specific:

1. **The canvas emits the bytes.** `lastFileAdded` for an image Excalidraw
   placed; `lastExternalDrop` for anything else — including GIFs, for the
   reason below. Both carry a `dataURL`.
2. **Python decodes and stores it.** `decode_data_url` → the storage backend's
   `put(key, mime, data)`, which returns a **URL**.
3. **The bytes live wherever the backend puts them.** In-process by default.
4. **The canvas is pointed at the URL.** `replaceFiles` for images; for other
   files the placeholder gets a `link`, and a GIF's placeholder is replaced by
   an `embeddable` whose iframe loads the stored file. Either way
   `externalizedSerializedData` comes back with every `data:` URI stripped —
   that is the payload you persist.

#### The storage backend is a seam

`lib/file_backends.py` defines it, and it is three methods:

```python
class FileBackend:
    def put(self, key, mime_type, data) -> str:  ...   # store; return a URL
    def get(self, key) -> tuple[str, bytes] | None: ...  # None if this app
                                                         # does not serve them
    def url_for(self, key) -> str: ...
```

`EXCALIDRAW_FILE_BACKEND` chooses one: `memory` (default) or `disk`
(`EXCALIDRAW_FILE_DIR`). An unknown name **raises at boot** rather than
falling back — a store that is silently not the one you configured is worse
than a failure to start.

For Cloudflare R2, S3 or a Postgres blob table, implement those three and
register it:

```python
from lib.file_backends import FileBackend, register_backend

class R2Backend(FileBackend):
    name = "r2"
    def put(self, key, mime_type, data):
        bucket.put_object(Key=key, Body=data, ContentType=mime_type)
        return self.url_for(key)
    def get(self, key):
        return None              # the CDN serves them; this app never does
    def url_for(self, key):
        return f"https://cdn.example.com/{key}"

register_backend("r2", R2Backend)
```

Nothing above storage changes. The canvas only ever needed a URL back.

**Two things change once the URL is not this app's origin**, and both are the
deployment's to solve rather than the component's. **CORS**: Excalidraw fetches
image bytes, so the bucket must allow your site's origin — a CDN that serves
`<img>` happily can still refuse a cross-origin fetch. And **lifetime**: the
default backend's caps exist because it holds bytes in a web process on a
512 MB container; a bucket has none of those constraints and should not
inherit limits sized for somebody else's.

#### Why GIFs take a different route

Excalidraw **rasterises a dropped GIF to a single still frame** before anything
downstream sees it. Measured here: a 123,069-byte GIF89a of 12 frames arrives
as a 2,820-byte PNG with none. So uploading what the canvas hands you stores a
still, and framing that in an iframe frames a still — the animation was lost at
the drop, not at the embed.

The rasterisation is also what freezes the tab on a large one. Dropping a
5.17 MB 600×600×20 GIF left the renderer unable to answer a debugger
evaluation at all — two 45-second timeouts — while the server sat idle at 32
callbacks and logged no error. It is decode work on the main thread, not I/O,
and no storage change touches it.

(Timer-based "scheduling lag" is **not** a usable measure here: a backgrounded
tab is throttled to ~1 s, so an idle page with no GIF reports the same figure
as a wedged one. An earlier draft of this note quoted those numbers before
that was checked against a control.)

So the component intercepts a GIF drop and sends the **original bytes** down
the `lastExternalDrop` path, exactly like a `.pdf` or a `.txt`. Excalidraw
never decodes it. This page then stores those bytes and puts an `embeddable`
where the placeholder was, so the browser animates the real file.

The trade is that a GIF is an embed rather than an image element: it is not
croppable or styleable on the canvas, and it needs the storage URL to be
reachable from the browser. That is the price of it moving at all.

### Overview

Keep canvas JSON small: uploads to external storage, base64 swapped for URLs.
Drop multiple images, or any non-image file, or a GIF — each takes the right
path automatically.

### Live demo

.. exec::docs.file-uploads.file_uploads
    :code: false

### Source

.. source::docs/file-uploads/file_uploads.py
    :defaultExpanded: false
    :withExpandedButton: true
