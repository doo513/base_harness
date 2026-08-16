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
| 00 | Research / contracts | COMPLETE (canonical retrospective reconstruction still open) |
| 01 | Truth + execution integrity | COMPLETE (canonical retrospective reconstruction still open) |
| 02 | Capability isolation + sealed oracle | PASS / EXITED + remediation hardening |
| 03 | Persistence + resume + reproducibility | PASS / EXITED (`v0.4.0`) + provenance hardening |
| 04 | Semantic verification | PASS / EXITED (`v0.5.0`) + claim-class hardening |
| 05 | Failure recovery | PASS / EXITED (`v0.6.0`) |
| 06 | Loop / deterministic progress control | PASS / EXITED (`v0.7.0`) + semantic-progress hardening |
| 07 | Context Governance | PASS / EXITED (`v0.8.0`) + trusted-context bounds |
| 08 | Retrieval / Memory Gateway | RELEASE SNAPSHOT (`v0.9.0`), exit pending same-commit CI |

Current package version: **v0.9.0**.

## Stage 08 release snapshot

Stage 08 introduces a bounded retrieval/evidence gateway without treating retrieval as truth or progress:

- Actor controls only explicit query text; Kernel owns normalized request framing, scope, top-k, provider/index identity, ranking contract, admission policy and durable request identity;
- the shipped local lexical gateway is deterministic and declares search read-only; descriptor mutation during search is fail-closed;
- retrieval items are provider/source/content bound, stored as content-addressed artifacts, and verified before admission and before model-visible projection;
- batch admission prepares and verifies the whole result set before a single live HarnessState-side commit, so a later candidate failure does not partially admit earlier candidates;
- admitted retrieval is durable in `RetrievalState`, independent from ordinary observations and verified facts;
- model-visible retrieval is always `untrusted_retrieval` with `instruction_authority=none`;
- retrieval cannot directly mutate verified facts, completion, recovery, or Stage-06 progress;
- result count, query/source/provider fields, content bytes, metadata, model-visible preview, durable item count and request history are bounded;
- supersession is an explicit Kernel transition; search ordering is not treated as freshness authority;
- resume fails closed on missing/tampered artifacts or provider/index/config drift.

The pre-release implementation at commit `a9fab5d446ff574d2bd090f51226f7f366585d15` passed **182 tests with 5 hosted-environment skips** and all Stage 03–08 plus remediation probes in GitHub Actions run `31954088822`. Release candidate `8bd4454d8f6d6ed7ec4ab568a70c9aca67629e06` (`v0.9.0rc1`) also passed the complete gate in run `31954351977`. The `v0.9.0` release snapshot must reproduce the gate before Stage 08 is marked PASS / EXITED.

## Guarantee boundaries

### Stage 02
Production isolation requires a successful live `runtime_probe`. Hosted-runner skips do not count as production isolation proof. Independent clean-host reproduction remains a coverage gap.

### Stage 03
Non-idempotent effects are at-most-once automatically executed: COMMITTED receipts deduplicate; PREPARED-only receipts halt/fail closed. No universal exactly-once claim. Environment provenance is stronger but does not claim every deployment image/VM is immutably reproduced.

### Stage 04
Claim-class contracts prevent undeclared semantic promotion, but the current synthetic matrix does not prove broad real-world semantic-verifier coverage.

### Stage 05
Recovery guarantees durable control transitions, not that recovery improves task success. A/B effectiveness benchmarking remains open.

### Stage 06
Novel successful bytes are activity, not progress. Verified fact transitions provide deterministic epistemic progress, but goal-relevant task/world progress authority remains an open design problem.

### Stage 07
Verified trusted-fact projection is now deterministically bounded without deleting durable truth. Oversized mandatory goal/control inputs still need an entry-time fail-closed or externalized representation policy.

### Stage 08
Retrieval is evidence only. Stage 08 does not claim semantic query planning, arbitrary remote-provider honesty, automatic memory writes, or universal filesystem transactions. Failed batch preparation can leave unreferenced content-addressed artifact files that have no state/truth authority but may require later garbage collection.

## Development rule

Use `research/verified-state-stage03` as the single continuing research branch. Do not create a branch per Stage. Every completed Stage must include code, tests/probes, machine-readable evidence, implementation/review/exit Markdown reports, and full regression. `main` remains preserved.
