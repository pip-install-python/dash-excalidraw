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

### Overview

Turn a natural-language prompt into an Excalidraw scene. Pick a provider —
Claude, ChatGPT or Gemini — write a prompt, hit generate; the result is
dispatched to the canvas via `command: updateScene` (no component remount).
Run the same prompt twice with different providers to compare output.

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
