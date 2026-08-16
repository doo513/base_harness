# Verified-State Harness — Current Agent Handoff

## Current status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE
Stage 02  PASS / EXITED
Stage 03  PASS / EXITED   v0.4.0
Stage 04  PASS / EXITED   v0.5.0
Stage 05  PASS / EXITED   v0.6.0
Stage 06  NEXT / NOT STARTED
```

## Stage 05 final evidence

Final candidate `v0.6.0-rc6`:

```text
commit                     c50a4bd15a86b3e26bf1fe52c15edde61738edd0
GitHub Actions             31936441736
pytest                     94 passed / 5 skipped
Stage 03 resume            4 / 4 PASS; duplicate=0
Stage 04 semantic          8 / 8 PASS; FP=0/FN=0
Stage 05 recovery          PASS
Stage 05 adversarial       PASS
Stage 05 terminal          PASS
Stage 05 crash-window      PASS
Stage 05 strategy-gen      PASS
```

Five skips are hosted-environment live Linux namespace tests. They do not replace Stage 02 production isolation evidence.

## Stage 05 guarantee boundary

The kernel durably schedules/applies recovery control transitions and terminal fail-closed states. It does **not** guarantee that an LLM semantically follows REPAIR/REPLAN, does not provide exactly-once Actor directive delivery, and does not transactionally roll back arbitrary external systems.

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
10. `../STAGE5_IMPLEMENTATION_REPORT.md`
11. `../STAGE5_EVIDENCE_MATRIX.md`
12. `../STAGE5_FINAL_REREVIEW.md`
13. `../STAGE5_EXIT_DECISION.md`

The next agent's first task is to re-review the v0.6.0 baseline and freeze the Stage 06 Progress Contract. Do not start with embeddings or an LLM similarity judge.
