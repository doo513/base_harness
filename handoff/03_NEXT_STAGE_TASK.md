# 03 — Next Stage Task

# Stage 03 — Persistence / Resume / Reproducibility

Goal: move from “checkpoint files exist” to **an interrupted run can actually resume safely and reproducibly**.

Required targets:
1. atomic checkpoint restore path
2. explicit run manifest
3. duplicate side-effect prevention / idempotency receipts
4. event replay and canonical state hash
5. checkpoint corruption detection + fail-closed recovery
6. state/event consistency checks
7. provenance for model/config/tool/runtime/task revision
8. public resume entry point

Required scenarios: forced termination after persisted transition; restart same run; continue without replaying committed external effects; corrupted/truncated checkpoint; event/checkpoint mismatch; duplicate external action; deterministic replay to same trusted-state hash; missing provenance field warning/failure.

Exit minimum:

```text
forced kill → resume succeeds
duplicate external action = 0
checkpoint corruption behavior demonstrated
deterministic replay state hash matches
```

Non-goals: RAG, vector DB, memory graph, subagent swarm, planner hierarchy, automatic skill learning, model router. Do not conflate checkpoint file with resume semantics, memory with state, or replay with re-executing side effects.
