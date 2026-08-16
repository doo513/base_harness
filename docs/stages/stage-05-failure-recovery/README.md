# Stage 05 — Failure Recovery

Status: **PASS / EXITED**  
Release: **v0.6.0**

## Result

Failure recovery is now a kernel-owned durable transition rather than a recommendation stored in logs.

```text
Failure
 -> typed route
 -> PENDING recovery
 -> immediate checkpoint
 -> apply before Actor
 -> APPLIED / SUPERSEDED
 -> immediate checkpoint
 -> Actor directive or terminal halt
```

## Implemented

- durable `RecoveryTransition` and `RecoveryStatus`;
- pending/history/directive/strategy/terminal recovery state;
- control-only REPAIR / OBSERVE / REPLAN / RETRY;
- logical-only ROLLBACK of targeted untrusted hypothesis;
- strategy generation and generation-scoped repeat counts;
- terminal CHECKPOINT_STOP for security, persistence ambiguity, and hard budget;
- immediate recovery scheduling/application checkpoints;
- resume-before-Actor ordering;
- explicit stateful-controller checkpoint protocol;
- recovery boundary budget recheck;
- meaningful-number-preserving failure signatures plus explicit `signature_key` override.

## Final candidate

`v0.6.0-rc6` — commit `c50a4bd15a86b3e26bf1fe52c15edde61738edd0`

GitHub Actions `31936441736`:

```text
94 passed / 5 skipped
Stage 03 direct probe       PASS
Stage 04 semantic probe     PASS
Stage 05 recovery probe     PASS
Stage 05 adversarial        PASS
Stage 05 terminal           PASS
Stage 05 crash-window       PASS
Stage 05 strategy generation PASS
```

## Important boundary

This Stage provides durable recovery **control semantics**. It does not prove that a model will follow a REPAIR/REPLAN directive semantically, and it does not roll back arbitrary external state.

See:
- `../../STAGE5_IMPLEMENTATION_REPORT.md`
- `../../STAGE5_EVIDENCE_MATRIX.md`
- `../../STAGE5_FINAL_REREVIEW.md`
- `../../STAGE5_EXIT_DECISION.md`
- `CONTRACT.md`
