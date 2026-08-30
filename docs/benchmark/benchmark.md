---
name: Benchmark
description: "Run one prompt across several efforts or token budgets at once and compare the drawings side by side."
endpoint: /benchmark
package: dash_excalidraw
category: Advanced
order: 5
icon: mdi:chart-box-outline
tier: auth
lastmod: 2026-08-09
---

.. llms_copy::Benchmark

.. toc::

### Overview

[AI agent](/ai-agent) answers *can it draw this?* This page answers the question
you have immediately afterwards: **what do I give up by turning the knob down?**

It sends one prompt to several settings at once and puts the drawings next to
each other. Element counts and token totals rank the runs; looking at them tells
you whether the extra tokens actually bought anything — which is not the same
question, and is the reason every cell renders a real canvas rather than a row
in a table.

### What the two axes mean

**Effort** is thinking depth. On Claude Opus 5 it is largely a cost-and-latency
control for this task: in a measured sweep, `high` cost 2.3× `low` and took 44%
longer to produce one extra element, and `medium` produced *fewer* elements than
`low`. Worth confirming on your own prompts — that is what the page is for.

**Max tokens** is the lever that moves output. On Opus 5 it bounds thinking
**and** response text together, so it is not a safety net but the main quality
dial: tripling it took the same prompt from 24 elements to 31.

Only one axis varies per run. Two moving variables make a comparison
unreadable, and a full grid is a combinatorial bill.

### Live demo

.. exec::docs.benchmark.benchmark
    :code: false

### Reading the results

Each panel shows the settings, the element count, wall time, token counts and an
estimated cost. The status line reports total wall time alongside what the same
run would have cost serially — the variants run **concurrently**, so a six-cell
matrix takes roughly one generation's time rather than six.

Three cautions before drawing conclusions:

- **Element count is a crude proxy for quality.** A busier diagram is not a
  better one. The canvases are there to be looked at.
- **These are single samples.** Model output varies run to run; repeat before
  trusting a small difference.
- **Cost figures are local estimates**, not a bill — they ignore cache-write
  premiums and any discount.

### Source

.. source::docs/benchmark/benchmark.py
    :defaultExpanded: false
    :withExpandedButton: true
