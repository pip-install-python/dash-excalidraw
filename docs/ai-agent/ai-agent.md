---
name: AI agent
description: Turn a natural-language prompt into an Excalidraw scene with Claude, ChatGPT or Gemini, and what it costs.
endpoint: /ai-agent
package: dash_excalidraw
category: Advanced
order: 4
icon: mdi:robot-outline
tier: auth
lastmod: 2026-09-10
---

.. llms_copy::AI agent

.. toc::

> **On this site these pages are documentation, not a hosted service.**
> excalidraw.2plot.dev carries no provider keys, so generation is disabled
> here and nothing below will spend anything. Everything on the page —
> streaming onto the canvas, the cost estimate, the Stop button, the daily
> spend ceiling — works when you run the repo locally with a `.env` holding a
> provider key. This is deliberate and not a fault.

### Overview

Turn a natural-language prompt into an Excalidraw scene. Pick a provider —
Claude, ChatGPT or Gemini — write a prompt, hit generate; the result is
dispatched to the canvas via `command: updateScene` (no component remount).
Run the same prompt twice with different providers to compare output.

Claude and ChatGPT runs **stream**: elements appear on the canvas as the
model closes each one, so you watch the scene being drawn rather than waiting
on a spinner and receiving it all at once. The status line counts shapes and
seconds as they land. Gemini has no streaming path in its SDK, so it still
returns the whole scene at the end — the page keeps that behaviour rather than
faking progress it cannot see.

Each provider is enabled only when its key is present, and the badges above
the controls say which name was looked for. The cost line under the button
prices the run **before** you click it: a typical figure and a ceiling, because
the max-token budget bounds the spend without determining it. Gemini has no
price on file here and says so rather than showing $0.00.

### Live demo

.. exec::docs.ai-agent.ai_agent
    :code: false

### Source

.. source::docs/ai-agent/ai_agent.py
    :defaultExpanded: false
    :withExpandedButton: true
