---
name: test
description: Run the project test suite with optional filtering
argument-hint: "[file or pattern]"
allowed-tools: Bash, Read, Grep
---

Run tests for dash-excalidraw.

## Steps

1. If $ARGUMENTS provided, filter to matching tests
2. Run: `pytest tests/ -v`
3. If failures found, read failing test files and suggest fixes
4. Report summary: total, passed, failed, skipped