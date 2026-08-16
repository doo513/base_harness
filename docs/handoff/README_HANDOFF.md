# Verified-State Harness — Current Agent Handoff

## Current status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  PASS / EXITED   v0.6.0
Stage 06  PASS / EXITED   v0.7.0
Stage 07  PASS / EXITED   v0.8.0
Stage 08  NEXT — Retrieval / Memory Gateway; contract not frozen
```

## Stage 07 release evidence

`v0.8.0` / release commit `e53c7d8e16c4fdfc814150026c0a9fa64df026e6` / Actions `31943274153`:

```text
installed package            0.8.0
pytest                       125 passed / 5 skipped
Stage 03 resume              4 / 4 PASS; duplicate=0
Stage 04 semantic            8 / 8 PASS; FP=0/FN=0
Stage 05 all probes          PASS
Stage 06 all probes          PASS
Stage 07 base                4 / 4 PASS
Stage 07 adversarial         6 / 6 PASS
Stage 07 resume              3 / 3 PASS
Stage 07 compatibility       3 / 3 PASS
zero-tolerance counters      all 0
```

Five skips are hosted-environment live Linux namespace tests and do not replace Stage 02 production isolation evidence.

## Stage 07 guarantee boundary

Stage 07 is deterministic Context Governance, not semantic relevance ranking. Optional/untrusted material is bounded, deduplicated, and authority-separated, but mandatory goal/trusted/control material is not subject to a universal lossy cap. `valid_until` is not wall-clock evaluated. Retrieved or remembered content is not trusted simply because it enters context.

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
10. `../STAGE7_PREFLIGHT_REREVIEW.md`
11. `../STAGE7_IMPLEMENTATION_REPORT.md`
12. `../STAGE7_EVIDENCE_MATRIX.md`
13. `../STAGE7_FINAL_REREVIEW.md`
14. `../STAGE7_EXIT_DECISION.md`
15. `../stages/stage-07-context-governance/CONTRACT.md`

The next task is Stage 08 baseline re-review and freezing the **Retrieval / Memory Admission Contract**. Do not start by selecting a vector database, RAG framework, embedding model, or autonomous memory writer.
