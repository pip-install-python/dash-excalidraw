---
name: status
description: Project health check -- git state, test results, and current context
allowed-tools: Bash, Read, Glob
---

Report on dash-excalidraw project health.

## Steps

1. **Git status**: branch, uncommitted changes, ahead/behind remote
2. **Run tests**: `pytest tests/ -v`
3. **Check context**: Read `.claude/context.md` for current project state
4. **Check for issues**: outdated dependencies, stale branches, unresolved TODOs
5. **Summarize** in a clear table