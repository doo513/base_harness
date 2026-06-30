# Agent Operating Rules

This repo is a Codex-first base harness. Work should be small, local, and easy for another agent to resume.

## Defaults

- Read `README.md`, `docs/architecture.md`, and the relevant skill before changing behavior.
- Keep project memory file-based in `state/` and `schemas/`.
- Use `rg` for text search and language-aware tools when available.
- Run `python3 scripts/validate_harness.py --strict` before claiming the harness is ready.

## Boundaries

- Do not add secrets, tokens, local HOME paths, or machine-specific absolute paths.
- Do not add a vector store, cloud runtime, managed-agent service, or fake MCP server.
- Do not bypass hook trust as a normal workflow.
- Do not mutate repository history or remotes without explicit approval.

## Validation

Use these checks for normal handoff:

```bash
python3 scripts/validate_harness.py --strict
python3 -m py_compile scripts/validate_harness.py .codex/hooks/common.py .codex/hooks/user_prompt_submit.py .codex/hooks/pre_tool_policy.py .codex/hooks/stop_guard.py
git status --short
```
