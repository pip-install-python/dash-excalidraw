---
name: AI agent
description: Turn a natural-language prompt into an Excalidraw scene with Claude or Gemini, and what it costs.
endpoint: /ai-agent
package: dash_excalidraw
category: Advanced
order: 4
icon: mdi:robot-outline
tier: auth
lastmod: 2026-08-08
---

.. llms_copy::AI agent

.. toc::

### Overview

Turn a natural-language prompt into an Excalidraw scene. Pick a provider,
write a prompt, hit generate — the result is dispatched to the canvas via
`command: updateScene` (no component remount). Run the same prompt twice with
different providers to compare output.

### Live demo

.. exec::docs.ai-agent.ai_agent
    :code: false

### Source

.. source::docs/ai-agent/ai_agent.py
    :defaultExpanded: false
    :withExpandedButton: true
