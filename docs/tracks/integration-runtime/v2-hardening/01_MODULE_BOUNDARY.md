# Module Boundary Hardening

## Situation

Coordinator and Core orchestration both retained mutable run state, while Host tools imported both packages directly.

## Reason

Candidate attestation was correct, but split ownership made transition order, recovery, and API enforcement difficult to maintain.

## Action

Run ownership moved behind `CoordinatorService`; Core state is held by a Coordinator-owned `WorkspaceCandidateStore`, Host access uses one facade, and an AST boundary checker rejects forbidden imports and package cycles.

## Result

TUI and headless consumers continue using Host status events while execution state has one authoritative owner and atomic interrupted-run snapshots.

## Evidence

The coordinator, core orchestration, Host facade, boundary script, package typechecks, and targeted orchestration tests form the promotion evidence for this phase.
