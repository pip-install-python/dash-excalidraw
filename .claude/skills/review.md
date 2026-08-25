---
name: review
description: Review recent changes for quality, security, and convention adherence
argument-hint: "[file or git ref]"
allowed-tools: Bash, Read, Grep, Glob
---

Review code changes for quality issues.

## Steps

1. Determine scope:
   - If $ARGUMENTS is a file path, review that file
   - If $ARGUMENTS is a git ref, review `git diff $ARGUMENTS`
   - If no argument, review uncommitted changes: `git diff`
2. Check each changed file against `.claude/rules/`
3. Look for: security issues, missing error handling, code style violations
4. Report findings in a table: severity, file:line, issue, suggestion
5. Give overall verdict: approve, request changes, or needs discussion