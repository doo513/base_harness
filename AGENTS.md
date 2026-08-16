# Verified-State Harness Agent Rules

This branch is the standalone development line for the new Verified-State Harness. `main` is the preserved legacy Base Harness and must not be modified as part of this research line.

## Mandatory workflow

1. Read `docs/handoff/README_HANDOFF.md` and `docs/handoff/02_CURRENT_STATUS.md` before implementation.
2. Re-review the current baseline before every new Stage.
3. Freeze the active Stage contract before changing that Stage's semantic axis.
4. Do not advance until targeted tests, adversarial probes, full regression, prior-Stage probes, and final re-review pass.
5. Actor output may propose or act, but only harness-owned verification/oracles may promote trusted truth or completion.
6. Recovery is kernel-owned; it may not directly execute Actor tools, manufacture verified facts, or replay ambiguous external effects.
7. Progress is kernel-owned control state; Actor narrative/speculative churn cannot self-declare progress.
8. Context selection may reduce what the Actor sees, but may not rewrite epistemic status, authority, goal constraints, acceptance criteria, or terminal control state.
9. Retrieval/memory material, if later implemented, is not trusted merely because it is retrieved. It must enter through Context Governance and may not directly commit verified facts or completion.
10. Never weaken an earlier Stage gate to make a later Stage easier.
11. Every completed Stage must add implementation, discovered-error/methodology, final re-review, evidence, and exit Markdown reports plus machine-readable evidence.
12. Use this one continuing research branch. Do not create a new branch per Stage unless the user explicitly changes this rule.
13. Keep `pyproject.toml` project version and `harness.__version__` identical; CI regression enforces this.

## Current state

- Stage 00: COMPLETE
- Stage 01: COMPLETE
- Stage 02: PASS / EXITED
- Stage 03: PASS / EXITED (`v0.4.0`)
- Stage 04: PASS / EXITED (`v0.5.0`)
- Stage 05: PASS / EXITED (`v0.6.0`)
- Stage 06: PASS / EXITED (`v0.7.0`) — deterministic Loop / Progress Control
- Stage 07: PASS / EXITED (`v0.8.0`) — Context Governance
- Stage 08: NEXT — Retrieval / Memory Gateway; contract not frozen

Do not describe Stage 06 as semantic progress understanding. Do not describe Stage 07 as semantic retrieval/relevance understanding. The next agent must preflight Stage 08 before adding RAG/vector storage/automatic memory.

See `docs/handoff/02_CURRENT_STATUS.md` for authoritative details.
