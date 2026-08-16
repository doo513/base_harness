# 03 — Next Stage Task

# Stage 05 — Failure Recovery

Version target: `v0.6.0` only after PASS.

## Entry condition

Stage 04 Semantic Verification must be PASS / EXITED with no known false semantic promotion path in the declared generic contract. Entry is satisfied by `v0.5.0`.

## Current defect to address

`FailureRouter` currently maps a `FailureKind` to a recommended `RecoveryAction`, and repeated failures may change the recommendation to `SWITCH_STRATEGY`. The runtime records this recommendation in failure history, but that is not equivalent to an actual recovery state transition.

## First action

Do not immediately add planners, loop detectors, or agents.

First freeze a **Recovery Transition Contract** specifying:

1. recovery authority owner;
2. legal transition for every RecoveryAction;
3. what trusted state may be rolled back or preserved;
4. checkpoint/event/receipt behavior during recovery;
5. repeat threshold and strategy-switch semantics;
6. budget accounting;
7. security/persistence failures that must halt rather than retry;
8. resume semantics for an interrupted recovery transition.

## Required direct scenarios

- `TOOL_ERROR` → repair transition without replaying committed external effect;
- `MISSING_INFO` → observe transition;
- `VERIFICATION_FAILED` → replan transition without promoting rejected claim;
- `HYPOTHESIS_REFUTED` → rollback transition;
- repeated same signature → strategy switch at declared threshold;
- `PERSISTENCE_ERROR` or ambiguous receipt → checkpoint-stop/fail closed;
- security violation → no automatic unsafe retry;
- forced interruption during recovery → deterministic resume;
- recovery event/checkpoint mismatch → fail closed.

## Exit minimum

```text
recovery recommendation changes actual runtime state     PASS
recovery transition is durably replayable                PASS
no truth/verification/oracle bypass                       PASS
no duplicate non-idempotent external action              PASS
repeated failure escalation deterministic                PASS
full Stage 01–04 regression                              PASS
```

## Non-goals

Semantic no-progress detection, optimization/budget policy research, RAG, skills, subagents, planner hierarchy, or model routing remain later work.
