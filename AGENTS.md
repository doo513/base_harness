# Verified-State Harness Agent Rules

This branch is the standalone development line for the new Verified-State Harness. `main` is the preserved legacy Base Harness and must not be modified as part of this research line.

## Mandatory workflow

1. Read `docs/handoff/README_HANDOFF.md` and `docs/handoff/02_CURRENT_STATUS.md` before implementation.
2. Re-review the current baseline before every new Stage.
3. Freeze the active Stage contract before changing that Stage's semantic axis.
4. Do not advance until targeted tests, adversarial probes, full regression, prior-Stage probes, and final re-review pass.
5. Preserve the invariant: Actor output may propose or act, but only harness-owned verification/oracles may promote trusted truth or completion.
6. Recovery is kernel-owned; it may not directly execute Actor tools, manufacture verified facts, or replay ambiguous external effects.
7. Progress is kernel-owned control state; Actor narrative/speculative churn cannot self-declare progress.
8. Never weaken an earlier Stage gate to make a later Stage easier.
9. Every completed Stage must add implementation, discovered-error/methodology, final re-review, evidence, and exit Markdown reports plus machine-readable evidence.
10. Use this one continuing research branch. Do not create a new branch per Stage unless the user explicitly changes this rule.

## Current state

- Stage 00: COMPLETE
- Stage 01: COMPLETE
- Stage 02: PASS / EXITED
- Stage 03: PASS / EXITED (`v0.4.0`)
- Stage 04: PASS / EXITED (`v0.5.0`)
- Stage 05: PASS / EXITED (`v0.6.0`)
- Stage 06: PASS CANDIDATE — `v0.7.0` release verification pending

Do not begin Stage 07 until the actual `v0.7.0` snapshot passes the complete release CI/probe matrix and Stage 06 Exit Decision is recorded.
