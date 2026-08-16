# Verified-State Harness

This research branch is the standalone implementation of the new harness architecture. `main` remains the preserved legacy Base Harness and is not the development line for this project.

## Core invariant

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success. Recovery and progress control are kernel-owned and may not bypass those gates.**

## Architecture

```text
Goal Contract -> Observation/Evidence -> Trusted Working State
-> Actor Decision -> Capability/Isolation Gate -> Tool Runtime
-> Evidence/Hypothesis -> VerificationContract -> Kernel State Commit

Actor Decision -> deterministic Progress Control
  -> verified fact semantic change OR novel integrity-checked successful evidence
  -> no-progress family/global windows
  -> typed NO_PROGRESS -> Stage 05 recovery

Failure -> RecoveryTransition(PENDING) -> durable checkpoint
-> Kernel recovery before Actor -> APPLIED/SUPERSEDED -> checkpoint
-> bounded directive OR terminal fail-closed halt

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
| 07 | Context Governance | NEXT / NOT STARTED |

Current package version: **v0.7.0**.

## Stage 06 result

Stage 06 adds deterministic, durable progress-control semantics:

- kernel-owned `ProgressPolicy` and checkpointed `ProgressState`;
- Actor decision family/exact identities resistant to cosmetic payload churn;
- Actor narrative/speculative churn excluded from progress authority;
- verified fact semantic-content progress that excludes evidence-reference metadata churn;
- successful observation novelty only after content-address integrity verification;
- historical successful evidence revalidation before the next Actor boundary;
- specific Stage 05 failure precedence over generic `NO_PROGRESS`;
- same-family and global alternating-family no-progress windows;
- strategy switch resets local windows but is not itself progress;
- identical evidence remains known after strategy switching;
- strategy exhaustion routes through Stage 05 terminal `ESCALATE`;
- progress policy participates in execution provenance and resume determinism.

The actual `v0.7.0` release snapshot passed **112 tests with 5 hosted-environment namespace skips** plus all Stage 03–06 direct probes in GitHub Actions run `31938225096`.

## Guarantee boundaries

### Stage 02
Production isolation requires a successful live `runtime_probe`. Hosted-runner skips do not count as production isolation proof.

### Stage 03
Non-idempotent effects are at-most-once automatically executed: COMMITTED receipts deduplicate; PREPARED-only receipts halt/fail closed. No universal exactly-once claim.

### Stage 04
Generic structured verification does not solve natural-language truth. Domain-semantic facts require domain-specific verifier coverage.

### Stage 05
Recovery guarantees durable **control transitions**, not guaranteed semantic repair by an LLM and not transactional rollback of arbitrary external systems.

### Stage 06
Progress control is deterministic/syntactic. Novel evidence or a newly verified fact is not automatically proven relevant to the active goal. Continually changing valid outputs can remain novel until the hard budget ends the run. Historical successful-evidence scanning also has a known cumulative performance cost.

## Development rule

Use `research/verified-state-stage03` as the single continuing research branch. Do not create a branch per Stage. Every completed Stage must include code, tests/probes, machine-readable evidence, implementation/review/exit Markdown reports, and full regression. `main` remains preserved.

## Next work

Stage 07 is **Context Governance**. The current Actor context exposes broad state/observation material directly. Before implementation, Stage 07 must freeze a **Context Projection Contract** defining trusted-vs-untrusted fields, freshness/staleness, bounded deterministic observation selection, raw-evidence retention, context-policy provenance, and the rule that context selection/compression may never rewrite truth authority.
