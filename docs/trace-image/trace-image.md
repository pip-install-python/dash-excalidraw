---
name: Trace an image
description: Upload a reference image and have a vision model redraw it as an Excalidraw scene, then compare the two side by side.
endpoint: /trace-image
package: dash_excalidraw
category: Advanced
order: 6
icon: mdi:image-search-outline
tier: auth
lastmod: 2026-09-10
---

.. llms_copy::Trace an image

.. toc::

> **On this site these pages are documentation, not a hosted service.**
> excalidraw.2plot.dev carries no provider keys, so generation is disabled
> here and nothing below will spend anything. Everything on the page —
> streaming onto the canvas, the cost estimate, the Stop button, the daily
> spend ceiling — works when you run the repo locally with a `.env` holding a
> provider key. This is deliberate and not a fault.

### Overview

[AI agent](/ai-agent) starts from a sentence. This page starts from a picture:
upload one, and a vision model is asked to rebuild it out of Excalidraw's
primitives. The reference sits on the left, the drawing on the right, so the
comparison is the output.

The interesting part is the constraint. Excalidraw has six element types —
rectangle, ellipse, diamond, text, arrow/line, freedraw — so a photograph
cannot be reproduced. The model has to decide what the image **is** and rebuild
that. A screenshot of a flowchart comes back as a flowchart. A photo of a cat
comes back as a disappointment, and that is a more useful thing to see than a
curated success.

### What traces well

| Reference | Result |
|:----------|:-------|
| Flowcharts, box-and-arrow diagrams | Usually close — the primitives match the source |
| Wireframes, UI mockups | Good structure, approximate text |
| Charts with clear axes and bars | Layout holds; exact values rarely do |
| Logos, simple icons | Recognisable when geometric, poor when organic |
| Photographs | Blocks of colour at best; this is the honest limit |

The prompt tells the model to prefer six clean shapes that capture the
arrangement over six hundred freedraw strokes that capture noise — the second
looks like effort and exhausts the token budget without improving the drawing.

### The controls

The same three levers as [AI agent](/ai-agent), because they matter here for
the same reasons:

- **Model** — only models that accept image input are listed, which was
  established by reading each provider's capability data rather than assuming.
  Claude and ChatGPT models are both offered.
- **Effort** — thinking depth. Tracing rewards more of it than diagram
  generation does: the model is reasoning about spatial relationships rather
  than emitting a familiar shape. Only levels a model actually accepts appear.
- **Max tokens** — covers thinking *and* output together. A dense reference
  needs a larger budget than a sentence-prompted diagram.

### Cost

The estimate above the button includes the image's own input tokens, which are
not negligible for a large upload — roughly `width x height / 750`. It is
shown before the run, not after, for the same reason as
[Benchmark](/benchmark): an estimate that arrives with the result is an apology
rather than a decision.

### Live demo

.. exec::docs.trace-image.trace_image
    :code: false

### Source

.. source::docs/trace-image/trace_image.py
    :defaultExpanded: false
    :withExpandedButton: true
