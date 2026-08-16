# Verified-State Harness — Current Agent Handoff

## Current status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  PASS / EXITED   v0.6.0
Stage 06  PASS CANDIDATE  v0.7.0 release verification pending
```

## Stage 06 final candidate evidence

`v0.7.0-rc3` / commit `3188ea75f7ca3d503cd8557cd7dd8bd562eaa2d4` / Actions `31937830666`:

```text
pytest                     112 passed / 5 skipped
Stage 03 resume            4 / 4 PASS; duplicate=0
Stage 04 semantic          8 / 8 PASS; FP=0/FN=0
Stage 05 all probes        PASS
Stage 06 base              3 / 3 PASS
Stage 06 adversarial       3 / 3 PASS
Stage 06 resume            3 / 3 PASS
Stage 06 boundary          4 / 4 PASS
Stage 06 strategy          6 / 6 PASS
zero-tolerance counters    all 0
```

Five skips are hosted-environment live Linux namespace tests and do not replace Stage 02 production isolation evidence.

## Stage 06 guarantee boundary

Stage 06 is deterministic/syntactic progress control, not semantic progress understanding. New canonical tool output or newly verified truth can still be irrelevant to the active goal. Continuously changing valid outputs can remain syntactically novel. Historical successful evidence is conservatively re-hashed before Actor continuation, with a known cumulative performance cost.

## Mandatory workflow

```text
Inspect current implementation/evidence
-> reproduce baseline
-> freeze active Stage contract
-> implement one semantic axis
-> targeted + adversarial tests
-> full regression + prior Stage probes
-> logic/security/integrity re-review
-> freeze evidence
-> implementation/error/methodology + final-review + exit MD
-> PASS/PARTIAL/FAIL
-> continue only on PASS
```

## Branch rule

Continue only on `research/verified-state-stage03`. Do not create a Stage branch. Do not modify `main` as part of this development line.

## Read order

1. `00_PROJECT_CONTEXT.md`
2. `01_ARCHITECTURE.md`
3. `02_CURRENT_STATUS.md`
4. `03_NEXT_STAGE_TASK.md`
5. `04_EXECUTION_PROTOCOL.md`
6. `05_VALIDATION_GATES.md`
7. `06_EVIDENCE_STANDARD.md`
8. `08_AGENT_OPERATING_RULES.md`
9. `15_DO_NOT_DO.md`
10. `../STAGE6_PREFLIGHT_REREVIEW.md`
11. `../STAGE6_IMPLEMENTATION_REPORT.md`
12. `../STAGE6_EVIDENCE_MATRIX.md`
13. `../STAGE6_FINAL_REREVIEW.md`
14. `../stages/stage-06-loop-progress/CONTRACT.md`

The immediate task is **release verification for `v0.7.0`**. Only after that succeeds and `STAGE6_EXIT_DECISION.md` is written may Stage 07 Context Governance begin.
