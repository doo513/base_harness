---
name: implement-work
description: Execute an approved plan in small edits while preserving verification and scope boundaries.
---

# Implement Work

Use this skill after a plan is approved or when a small task is ready for direct execution.

## Steps

1. Confirm the active plan and Git state.
2. Reproduce the changed behavior before editing when practical.
3. Make focused edits that match existing repository conventions.
4. Keep generated caches, scratch files, and drafts out of tracked files.
5. Run the relevant validator or hook checks after each meaningful slice.

## Output

Leave implemented files and a clear validation trail.

## Boundaries

Do not run destructive Git commands or mutate remotes without explicit user approval.
