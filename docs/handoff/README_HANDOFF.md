# Verified-State Harness — Current Agent Handoff

Historical Stage 02 PARTIAL material remains preserved in the archive. Stage 02 was subsequently closed by the production Linux namespace backend and direct attack probes.

## Current status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE for scoped P0 defects
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  NEXT / NOT STARTED
```

## Most recent evidence

Stage 04 promotion candidate `v0.5.0-rc3`:

```text
GitHub Actions run         31934328945
pytest                     69 passed / 5 skipped
semantic matrix            8 / 8 PASS
false positives            0
false negatives            0
level inflation            blocked
artifact content tamper    blocked
semantic-key masquerade    blocked
cross-version resume       blocked
```

The five skips are live Linux namespace tests on a hosted environment that could not establish production `runtime_probe`; they do not replace Stage 02 direct production evidence.

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

## Branch rule

Use the existing `research/verified-state-stage03` branch as the single continuing development branch. Do not create a new Stage branch. `main` remains the preserved legacy Base Harness.

## Next agent read order

1. `00_PROJECT_CONTEXT.md`
2. `01_ARCHITECTURE.md`
3. `02_CURRENT_STATUS.md`
4. `03_NEXT_STAGE_TASK.md`
5. `04_EXECUTION_PROTOCOL.md`
6. `05_VALIDATION_GATES.md`
7. `06_EVIDENCE_STANDARD.md`
8. `08_AGENT_OPERATING_RULES.md`
9. `15_DO_NOT_DO.md`
10. `../STAGE4_IMPLEMENTATION_REPORT.md`
11. `../STAGE4_FINAL_REREVIEW.md`
12. `../STAGE4_EXIT_DECISION.md`

The next agent's first task is Stage 05 contract review, not feature expansion.
