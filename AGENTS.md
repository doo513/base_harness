# Verified-State Harness Agent Rules

This branch is the standalone development line for the new Verified-State Harness. `main` is the preserved legacy Base Harness and must not be modified as part of this research line.

## Mandatory workflow

1. Read `docs/handoff/README_HANDOFF.md` and `docs/handoff/02_CURRENT_STATUS.md` before implementation.
2. Do not advance a Stage until its entry contract, tests, adversarial probes, full regression, and final re-review pass.
3. Preserve the invariant: Actor output may propose or act, but only harness-owned verification/oracles may promote trusted truth or completion.
4. Never weaken Stage 01–03 gates to make a later Stage easier.
5. Every completed Stage must add/update Markdown reports under `docs/stages/` and implementation/evidence reports under `docs/` plus machine-readable evidence under `evidence/`.
6. Use one continuing research branch. Do not create a new branch per Stage unless the user explicitly changes this rule.

## Current state

- Stage 00: COMPLETE
- Stage 01: COMPLETE
- Stage 02: PASS / EXITED
- Stage 03: PASS / EXITED (`v0.4.0`)
- Stage 04: NEXT / NOT STARTED

See `docs/handoff/02_CURRENT_STATUS.md` for authoritative details.
