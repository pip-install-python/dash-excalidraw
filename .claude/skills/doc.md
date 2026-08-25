---
name: doc
description: Generate or update documentation for a module or function
argument-hint: "<file-path>"
allowed-tools: Read, Glob, Grep, Edit, Write
---

Generate documentation for the specified file or module.

## Steps

1. Read the target file ($ARGUMENTS)
2. Analyze exports, classes, functions, and their signatures
3. Generate appropriate documentation (docstrings, JSDoc, rustdoc, etc.)
4. If the module is complex, create or update a companion markdown file
5. Report what was documented