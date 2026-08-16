# Verified-State Harness

This research branch is the standalone implementation of the new harness architecture. `main` remains the preserved legacy Base Harness and is not the development line for this project.

## Core invariant

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success. Recovery, progress control, and context projection are kernel-governed and may not bypass those gates.**

## Architecture

```text
Goal Contract -> Observation/Evidence -> Trusted Working State
-> Context Governor -> Actor Decision
-> Capability/Isolation Gate -> Tool Runtime
-> Evidence/Hypothesis -> VerificationContract -> Kernel State Commit

Actor Decision -> deterministic Progress Control
  -> verified fact semantic change OR novel integrity-checked successful evidence
  -> no-progress family/global windows -> typed recovery

Failure -> durable RecoveryTransition -> Kernel recovery before Actor
-> APPLIED/SUPERSEDED -> bounded directive OR terminal halt

Completion request -> Completion Oracle -> Kernel accepts/rejects
```

## Stage status

| Stage | Scope | Status |
|---|---|---|
| 00 | Research / contracts | COMPLETE |
| 01 | Truth + execution integrity | COMPLETE |
| 02 | Capability isolation + sealed oracle | PASS / EXITED |
| 03 | Persistence + resume + reproducibility | PASS / EXITED (`v0.4.0`) |
| 04 | Semantic verification | PASS / EXITED (`v0.5.0`) |
| 05 | Failure recovery | PASS / EXITED (`v0.6.0`) |
| 06 | Loop / deterministic progress control | PASS / EXITED (`v0.7.0`) |
| 07 | Context Governance | PASS / EXITED (`v0.8.0`) |
| 08 | Retrieval / Memory Gateway | NEXT / CONTRACT NOT FROZEN |

Current package version: **v0.8.0**.

## Stage 07 result

Stage 07 makes Context Governor the single runtime projection boundary:

- mandatory goal, acceptance, constraints, pinned constraints, current trusted facts and critical control state are retained;
- verified/current truth is separated from hypotheses, observations, refutations and failure text;
- superseded facts are not exposed as current truth;
- optional/untrusted previews and tool descriptions are deterministically bounded;
- duplicate observations are collapsed while raw artifact references remain available;
- untrusted text has no instruction authority in the built-in model path;
- ContextPolicy is part of resume provenance;
- same state + same policy projects deterministically after resume;
- trusted Controller legacy access for moved fields is detached and non-serialized;
- actual Stage-07 keys have one governed Python/JSON value;
- dormant raw context implementation was removed;
- build/runtime version metadata is regression-locked.

The actual `v0.8.0` release snapshot passed **125 tests with 5 hosted-environment namespace skips** plus all Stage 03–07 direct probes in GitHub Actions run `31943274153`.

## Guarantee boundaries

### Stage 02
Production isolation requires a successful live `runtime_probe`. Hosted-runner skips do not count as production isolation proof.

### Stage 03
Non-idempotent effects are at-most-once automatically executed: COMMITTED receipts deduplicate; PREPARED-only receipts halt/fail closed. No universal exactly-once claim.

### Stage 04
Generic structured verification does not solve natural-language truth. Domain-semantic facts require domain-specific verifier coverage.

### Stage 05
Recovery guarantees durable control transitions, not guaranteed semantic repair by an LLM and not transactional rollback of arbitrary external systems.

### Stage 06
Progress control is deterministic/syntactic. Novel evidence or verified truth is not automatically proven relevant to the active goal.

### Stage 07
Context selection is deterministic governance, not semantic retrieval quality. Mandatory trusted/control content is not subject to a universal hard truncation limit, `valid_until` is not wall-clock evaluated, and retrieval/memory content is not trusted merely because it enters context.

## Development rule

Use `research/verified-state-stage03` as the single continuing research branch. Do not create a branch per Stage. Every completed Stage must include code, tests/probes, machine-readable evidence, implementation/review/exit Markdown reports, and full regression. `main` remains preserved.

## Next work

Stage 08 candidate is **Retrieval / Memory Gateway**. Before implementing RAG, a vector store, or automatic memory writes, freeze an admission contract defining provenance, integrity, deterministic query inputs, trust level, write authority, context-budget interaction, resume behavior, deletion/supersession semantics, and the rule that retrieved/remembered material cannot directly mutate verified facts or completion state.
