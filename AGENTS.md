# Verified-State Harness Agent Rules

`develop` is the active development branch. `preprocessing` is the frozen pre-integration snapshot and must not be mutated. `main` is the promotion target and is changed only after validated integration work is explicitly promoted.

## Mandatory workflow

1. Read `docs/handoff/README_HANDOFF.md` and `docs/handoff/02_CURRENT_STATUS.md` before implementation.
2. Re-review the current baseline before each integration phase.
3. Freeze the phase contract before changing its semantic axis.
4. Do not advance until targeted tests, adversarial checks where applicable, full regression, prior-Stage probes, and structural re-review pass.
5. Actor output may propose or act, but only harness-owned verification/oracles may promote trusted truth or completion.
6. Recovery is kernel-owned; it may not directly execute Actor tools, manufacture verified facts, or replay ambiguous external effects.
7. Progress is kernel-owned control state; Actor narrative/speculative churn cannot self-declare progress.
8. Context selection may reduce what the Actor sees, but may not rewrite epistemic status, authority, goal constraints, acceptance criteria, or terminal control state.
9. Retrieval/memory material is not trusted merely because it is retrieved or remembered. It must enter through Context Governance and may not directly commit verified facts or completion.
10. Never weaken an earlier Stage gate to make integration easier.
11. Every completed integration phase must leave Markdown evidence describing rationale, implementation, validation, structural review, and remaining limitations.
12. Continue on `develop`; do not create per-phase branches unless the user explicitly changes this rule.
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
- Stage 08: PASS / EXITED (`v0.9.0`) — Retrieval / Memory Gateway
- Current package freeze line: `0.9.1`
- Current work: post-Stage08 integration/runtime track; no Stage 09 is created.

Do not describe Stage 06 as semantic progress understanding, Stage 07 as semantic relevance ranking, or Stage 08 as autonomous trusted memory. Model, tool, MCP/plugin, workspace, agent-control, and domain integrations must preserve the verified-state kernel boundary.

See `docs/handoff/02_CURRENT_STATUS.md` and `docs/tracks/integration-runtime/README.md`.
