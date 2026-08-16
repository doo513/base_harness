# Stage 06 — Loop / Progress Control

Status: **PASS / EXITED**  
Release: `v0.7.0`  
Release commit: `02d0b262756cd8f7eb32b6757f3b3066d94b63f1`  
Release Actions: `31938225096`

## Purpose

Stage 06 adds deterministic, kernel-owned progress accounting on top of Stage 05 recovery. It bounds inspectable repeated/no-progress behavior without trusting Actor self-reporting or introducing an LLM/embedding progress judge.

## Implemented control model

```text
Actor Decision
-> trusted baseline
-> existing dispatch / verification / failure gates
-> deterministic progress evaluation
   ├─ verified fact semantic content changed
   └─ novel integrity-checked successful observation content
-> no progress windows
   ├─ same decision family
   └─ global alternating-family streak
-> FailureKind.NO_PROGRESS
-> Stage 05 recovery
-> repeated failure: SWITCH_STRATEGY
-> generation exhaustion: STRATEGY_EXHAUSTED -> ESCALATE
```

## Important boundaries

Progress is not truth. Stage 06 cannot commit a fact or accept completion.

Actor narrative, speculative state churn, failed output, recovery transitions, evidence-ref metadata churn, and strategy switches do not independently count as progress.

Novel successful evidence is a deterministic syntactic signal. Stage 06 does **not** claim that novelty is semantically useful or goal-relevant.

## Release evidence

```text
pytest                             112 passed / 5 skipped
Stage 03 resume                    4 / 4 PASS
Stage 04 semantic                  8 / 8 PASS; FP=0/FN=0
Stage 05 all direct probes         PASS
Stage 06 base                      3 / 3 PASS
Stage 06 adversarial               3 / 3 PASS
Stage 06 resume                    3 / 3 PASS
Stage 06 boundary                  4 / 4 PASS
Stage 06 strategy                  6 / 6 PASS
```

All Stage 06 zero-tolerance counters in the declared matrices are 0.

The five skips are hosted-runner live Linux namespace tests and are not counted as Stage 02 production isolation proof.

See:

- `CONTRACT.md`
- `../../STAGE6_PREFLIGHT_REREVIEW.md`
- `../../STAGE6_IMPLEMENTATION_REPORT.md`
- `../../STAGE6_EVIDENCE_MATRIX.md`
- `../../STAGE6_FINAL_REREVIEW.md`
- `../../STAGE6_EXIT_DECISION.md`

## Next Stage

**Stage 07 — Context Governance** begins with a Context Projection Contract. RAG, embeddings, long-term memory, and LLM summarization remain outside scope until that trust/projection boundary is frozen and validated.
