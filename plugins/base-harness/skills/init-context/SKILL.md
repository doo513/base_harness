---
name: init-context
description: Build a concise working context for a Codex task before planning or editing.
---

# Init Context

Use this skill when starting a new task in the harness or resuming after a context transition.

## Steps

1. Read `AGENTS.md`, `README.md`, and the docs relevant to the task.
2. Inspect `state/brief.md`, `state/goals.json`, and `state/task-state.json`.
3. Check `git status --short` and `git remote get-url origin`.
4. Search the repository with `rg` for files related to the requested behavior.
5. Summarize the active goal, constraints, touched surfaces, and validation commands.

## Output

Produce a short context note with the active goal, relevant files, risks, and next validation step.

## Boundaries

Do not edit files from this skill. Do not invent state that is not present in the repository.

