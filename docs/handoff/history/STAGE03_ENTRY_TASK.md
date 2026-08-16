# 03 — Next Stage Task

# Stage 03 — Persistence / Resume / Reproducibility

## Goal

Move from “checkpoint files exist” to **an interrupted run can actually resume safely and reproducibly**.

## Entry requirement

Stage 02 must be PASS with direct evidence. This condition is now satisfied in the rc2 evidence set; re-run it before making security-boundary changes that could invalidate the result.

## Required implementation targets

1. atomic checkpoint restore path, not save-only
2. explicit run manifest
3. duplicate side-effect prevention / idempotency receipt strategy
4. event replay and canonical state hash
5. checkpoint corruption detection and recovery/fail-closed behavior
6. state/event consistency checks
7. provenance capture for model/config/tool/runtime/task revision
8. exact resume entry point exposed through runtime/CLI or equivalent public API

## Required adversarial/integration scenarios

At minimum demonstrate:

- forced process termination after a persisted state transition
- restart from the same run directory
- successful continuation without replaying already-committed external effects
- corrupted/truncated checkpoint
- event/checkpoint mismatch
- duplicate external action attempt
- deterministic replay to the same trusted-state hash for the deterministic test fixture
- missing provenance field causing an explicit reproducibility warning/failure according to contract

## Exit criteria inherited from roadmap

```text
forced kill → resume succeeds
duplicate external action = 0
checkpoint corruption recovery/fail-closed behavior demonstrated
deterministic replay state hash matches
```

Add precise measurable criteria before implementation; do not rely on those four lines alone if ambiguities remain.

## Non-goals

Do not add merely for feature breadth:

- RAG
- vector DB
- memory graph
- subagent swarm
- planner hierarchy
- automatic skill learning
- model router

Do not conflate:

```text
checkpoint file != resume semantics
memory != state
replay != re-executing side effects
```
