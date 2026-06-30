# Handoff Checklist

Use this checklist before handing off harness changes.

- `python3 scripts/validate_harness.py --strict` passes.
- Hook happy and failure fixtures behave as documented in `docs/verification.md`.
- `git status --short --ignored` shows only intended tracked and ignored paths.
- `git remote get-url origin` returns `https://github.com/doo513/base_harness.git`.
- No secrets, local HOME paths, generated caches, or local trace artifacts are left in tracked files.
