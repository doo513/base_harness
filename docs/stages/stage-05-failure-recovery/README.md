# Stage 05 — Failure Recovery

Status: **NEXT / NOT STARTED**.

## Entry condition

Stage 04 Semantic Verification must be PASS / EXITED. Satisfied by `v0.5.0`.

## Problem statement

The current `FailureRouter` maps failure kinds to a `RecoveryAction` and changes the recommendation after repeated failures, but the runtime mostly records that recommendation. The next research question is whether recovery can become a **kernel-owned, durable transition** rather than advisory text.

## First task

Before implementation, freeze a Recovery Transition Contract covering:

- which component owns recovery authorization;
- allowed state mutations per recovery action;
- rollback target and evidence requirements;
- interaction with checkpoint/event/receipt state;
- repeat/no-progress escalation rules;
- recovery budget accounting;
- how a recovery transition is prevented from bypassing verification, tool isolation, or completion oracle gates.

## Required scenarios

At minimum:

```text
tool error            → repair transition
missing information   → observe transition
verification failure  → replan transition
refuted hypothesis    → rollback transition
repeated same failure → switch strategy once threshold is reached
persistence ambiguity → checkpoint-stop / fail closed
security violation    → no unsafe automatic retry
resume during recovery→ deterministic recovery state
```

## Non-goals

Stage 05 is not yet semantic loop detection, token optimization, RAG, skill learning, planner hierarchy, or subagent orchestration.

## Exit direction

A recovery recommendation printed in logs is insufficient. PASS requires direct evidence that the runtime transition changes safely and durably, with no bypass of Stage 01–04 gates.
