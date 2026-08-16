# Verified-State Harness

This research branch is the standalone implementation of the new harness architecture. `main` remains the preserved legacy Base Harness and is not the development line for this project.

## Core invariant

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success. Recovery, progress control, context projection, and retrieval admission are kernel-governed and may not bypass those gates.**

## Architecture

```text
Goal Contract -> Observation/Evidence -> Trusted Working State
-> Context Governor -> Actor Decision
-> Capability/Isolation Gate -> Tool Runtime
-> Evidence/Hypothesis -> VerificationContract -> Kernel State Commit

Actor Decision -> deterministic Progress Control
  -> activity novelty: credit 0
  -> verified fact transition: epistemic progress
  -> no-progress family/global windows -> typed recovery

Actor retrieval request
  -> Kernel-owned scope/top-k/provider/ranking/admission/request identity
  -> deterministic read-only Gateway
  -> content-addressed verified admission
  -> durable RetrievalState
  -> Context Governor as untrusted_retrieval / instruction_authority=none
  -> retrieval itself gives progress credit 0

Failure -> durable RecoveryTransition -> Kernel recovery before Actor
-> APPLIED/SUPERSEDED -> bounded directive OR terminal halt

Completion request -> Completion Oracle -> Kernel accepts/rejects
```

## Stage status

| Stage | Scope | Status |
|---|---|---|
| 00 | Research / contracts | HISTORICAL COMPLETE — retrospective canonical genealogy reconstructed |
| 01 | Truth + execution integrity | HISTORICAL COMPLETE — retrospective canonical genealogy reconstructed |
| 02 | Capability isolation + sealed oracle | PASS / EXITED + remediation hardening |
| 03 | Persistence + resume + reproducibility | PASS / EXITED (`v0.4.0`) + provenance hardening |
| 04 | Semantic verification | PASS / EXITED (`v0.5.0`) + claim-class hardening |
| 05 | Failure recovery | PASS / EXITED (`v0.6.0`) + controlled effectiveness A/B evidence |
| 06 | Loop / deterministic progress control | PASS / EXITED (`v0.7.0`) + semantic-progress hardening |
| 07 | Context Governance | PASS / EXITED (`v0.8.0`) + trusted-context bounds |
| 08 | Retrieval / Memory Gateway | **PASS / EXITED (`v0.9.0`)** |

Current package version: **v0.9.0**.

Stage00/01 canonical directories are retrospective provenance packages. They do not claim the labels/contracts existed in the original archive artifacts; missing archive contents are not reconstructed from memory.

## Stage 08 result

Stage 08 adds a bounded retrieval/evidence gateway without treating retrieval as truth or progress. Release commit `a5645fc9d059afd12088ee1c4751c0250c8a5206` built and installed `verified-state-harness 0.9.0` and passed **182 tests / 5 hosted-environment skips** plus all Stage 03–08 and remediation probes in GitHub Actions run `31954492789`.

## Guarantee boundaries

### Stage 02
Production isolation requires a successful live `runtime_probe`. Hosted-runner skips do not count as production isolation proof. Independent clean-host reproduction remains a coverage gap.

### Stage 03
Non-idempotent effects are at-most-once automatically executed: COMMITTED receipts deduplicate; PREPARED-only receipts halt/fail closed. No universal exactly-once claim. Environment provenance is stronger but does not claim every deployment image/VM is immutably reproduced.

### Stage 04
Claim-class contracts prevent undeclared semantic promotion, but the current synthetic matrix does not prove broad real-world semantic-verifier coverage.

### Stage 05
Recovery guarantees durable control transitions. A frozen deterministic matched A/B benchmark demonstrated positive causal utility: production Recovery completed 3/3 recoverable scenarios while a conservative no-automatic-recovery baseline completed 0/3, with zero terminal-safety regressions. This does **not** establish broad real-world or LLM-agent effectiveness; natural corpus validation remains open.

### Stage 06
Novel successful bytes are activity, not progress. Verified fact transitions provide deterministic epistemic progress, but goal-relevant task/world progress authority remains an open design problem.

### Stage 07
Verified trusted-fact projection is deterministically bounded without deleting durable truth. Oversized mandatory goal/control inputs still need an entry-time fail-closed or externalized representation policy.

### Stage 08
Retrieval is evidence only. Stage 08 does not claim semantic query planning, arbitrary remote-provider honesty, automatic memory writes, or universal filesystem transactions. Failed batch preparation can leave unreferenced content-addressed artifact files that have no state/truth authority but may require later garbage collection.

## Development rule

Use `research/verified-state-stage03` as the single continuing research branch. Do not create a branch per Stage. Every completed Stage must include code, tests/probes, machine-readable evidence, implementation/review/exit Markdown reports, and full regression. `main` remains preserved.
