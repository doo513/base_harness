# Verified-State Harness — Current Agent Handoff

Historical Stage 02 PARTIAL material remains preserved in the archive. Stage 02 was subsequently closed by the production Linux namespace backend and direct attack probes.

## Current status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE for scoped P0 defects
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED
Stage 04  NEXT / NOT STARTED
```

Current implementation version: `v0.4.0`.

## Stage 03 evidence

```text
12 Stage 03 tests PASS
59 full pytest tests PASS
4/4 direct resume probes PASS
duplicate external actions = 0
checkpoint corruption = fail closed
event/checkpoint mismatch = fail closed
canonical replay state hash = match
Stage 02 attack regression = PASS
compileall = PASS
```

Stage 03 guarantee boundary:

```text
COMMITTED non-idempotent receipt -> deduplicate, never automatically execute again
PREPARED-only receipt            -> ambiguous, halt/fail closed
```

Do not rewrite this as a universal exactly-once guarantee.

## Project objective

Build a **General Harness Kernel + Domain Profile** architecture where Actor output may propose and act, but trusted truth/completion/state transitions remain harness-owned and evidence-gated.

## Mandatory workflow

```text
Inspect current implementation/evidence
→ Reproduce baseline
→ Freeze active stage contract
→ Implement active stage only
→ Unit/integration/adversarial tests
→ Full regression
→ Logic/security/integrity re-review
→ Freeze raw evidence
→ Detailed stage report + decision log + evidence matrix
→ PASS/PARTIAL/FAIL
→ Continue only on PASS
```

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
10. Stage 03 reports/evidence

Historical Stage 03 entry contract is preserved at `history/STAGE03_ENTRY_TASK.md`.

The next agent must re-review Stage 04 semantic-verification requirements before implementing them.
