# 02 — Current Status

## Stage status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE for scoped P0 defects
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  PASS / EXITED   v0.6.0
Stage 06  NEXT / NOT STARTED
```

## Stage 02 boundary

`LinuxNamespaceSandboxBackend` is production-isolated only when live `runtime_probe` succeeds. Five current hosted-CI namespace tests skip because that environment cannot establish the production probe; these skips are not treated as PASS evidence and do not replace the previously recorded direct Stage 02 attack evidence.

## Stage 03 guarantee

```text
COMMITTED non-idempotent receipt -> deduplicate
PREPARED-only receipt            -> ambiguous, halt/fail closed
```

This is at-most-once automatic execution, not universal exactly-once semantics.

## Stage 04 guarantee

Domain `VerificationContract` controls verifier coverage/strength/evidence requirements. Generic structured assertions are evidence-integrity checked and cannot masquerade as arbitrary domain-semantic facts. Natural-language truth is not generically solved.

## Stage 05 — Failure Recovery

Status: **PASS / EXITED**.  
Version: `v0.6.0`.

Implemented:
- execution-semantic resume provenance hardening (`v0.5.1`);
- explicit stateful-controller checkpoint protocol (`v0.5.2`);
- durable `RecoveryTransition` PENDING/APPLIED/SUPERSEDED state;
- immediate scheduling/application checkpoints;
- recovery-before-Actor ordering on resume;
- logical-only speculative rollback;
- explicit retry-safety gate;
- terminal fail-closed recovery for security/persistence/budget;
- generation-scoped repeat escalation;
- failure/recovery audit linkage and budget-boundary checks.

Final candidate evidence (`v0.6.0-rc6`, commit `c50a4bd15a86b3e26bf1fe52c15edde61738edd0`, Actions `31936441736`):

```text
pytest                             94 passed / 5 skipped
Stage 03 resume probe              4 / 4 PASS
duplicate external actions        0
Stage 04 semantic matrix           8 / 8 PASS
Stage 04 FP / FN                   0 / 0
Stage 05 base recovery             PASS
Stage 05 adversarial               PASS
Stage 05 terminal                  PASS
Stage 05 crash-window              PASS
Stage 05 strategy generation       PASS
unsafe automatic retries           0
verified-fact recovery mutations   0
ambiguous external executions      0
lost scheduled recoveries          0
hard-budget step overshoot          0
```

Important scope: Stage 05 proves durable recovery-control state, not guaranteed LLM semantic repair or external transaction rollback.

## Current unresolved work

The next allowed Stage is **Stage 06 — Loop / Progress Control**.

Before implementation, freeze a Progress Contract defining kernel-observable progress, no-progress identity, generation/reset semantics, escalation policy, and interaction with Stage 05 recovery. Do not begin with an embedding/LLM similarity heuristic.
