---
name: plan-work
description: Turn a user request into a decision-complete implementation plan with verification gates.
---

# Plan Work

Use this skill when scope spans multiple files, architecture choices, or workflow changes.

## Steps

1. Reuse the context from `init-context`.
2. Define must-have outcomes, non-goals, and explicit approval gates.
3. Split implementation into small verifiable tasks.
4. Define happy, edge, and regression checks for each risky task.
5. Write a short plan in `state/` or `docs/` only when the work is substantial enough to need handoff.

## Output

Produce a plan that another Codex session can execute without more interview.

## Boundaries

Do not hide unresolved product decisions. Do not include repository publication as an automatic step.
