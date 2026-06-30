---
name: verify-work
description: Validate harness changes through CLI, hook, and validation surfaces.
---

# Verify Work

Use this skill before claiming implementation is complete.

## Steps

1. Run `python3 scripts/validate_harness.py --strict`.
2. Run hook happy and failure fixtures from `docs/verification.md`.
3. Compile Python scripts with `python3 -m py_compile`.
4. Inspect workspace status and files.
5. Record validation results and any residual risks.

## Output

Produce a verification summary with commands run and pass/fail results.

## Boundaries

Do not weaken validators to pass. Do not ignore a blocking hook or schema failure.

