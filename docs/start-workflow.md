# Start Workflow

Use this flow when beginning a new task in this harness.

1. Read `AGENTS.md`, `README.md`, and `docs/architecture.md`.
2. Confirm the current state:

```bash
python3 scripts/validate_harness.py --strict
git status --short
git remote get-url origin
```

3. Update `state/brief.md` or `state/goals.json` only when the task changes the working goal.
4. For problem-file intake, run or test `run_intake_workflow`.
5. Implement small changes.
6. Run harness tests, hook checks when relevant, and strict validation before handoff.

## Hook Trust

Project-local hooks load only after the project `.codex/` layer is trusted. In Codex CLI, use `/hooks` to inspect new or changed hook definitions, review the command paths, and trust the current hook hash. Do not make bypass flags the default workflow.
