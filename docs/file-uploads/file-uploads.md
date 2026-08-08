---
name: File uploads
description: "Keep canvas JSON small: push pasted images to external storage and swap the base64 for URLs."
endpoint: /file-uploads
package: dash_excalidraw
category: Advanced
icon: mdi:cloud-upload-outline
---

.. llms_copy::File uploads

.. toc::

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
