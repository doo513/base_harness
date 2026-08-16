# Verified-State Harness

This research branch is the standalone implementation of the new harness architecture. `main` remains the preserved legacy Base Harness and is not the development line for this project.

## Core invariant

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success. Recovery is kernel-owned and may not bypass those gates.**

## Architecture

```text
Goal Contract -> Observation/Evidence -> Trusted Working State
-> Actor Decision -> Capability/Isolation Gate -> Tool Runtime
-> Evidence/Hypothesis -> VerificationContract -> Kernel State Commit

Failure -> RecoveryTransition(PENDING) -> durable checkpoint
-> Kernel recovery before Actor -> APPLIED/SUPERSEDED -> checkpoint
-> bounded directive OR terminal fail-closed halt

Completion request -> Completion Oracle -> Kernel accepts/rejects

Persistence: manifest + hash-chained events + atomic checkpoint
             + side-effect receipts + controller runtime state
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
| 06 | Loop / Progress Control | NEXT / NOT STARTED |

Current package version: **v0.6.0**.

## Stage 05 result

Stage 05 adds durable kernel-owned recovery-control transitions:

- typed `RecoveryTransition` state with PENDING/APPLIED/SUPERSEDED;
- immediate persistence when recovery is scheduled and applied;
- recovery-before-Actor ordering on resume;
- control-only REPAIR/OBSERVE/REPLAN/RETRY;
- logical-only rollback of targeted untrusted hypotheses;
- terminal fail-closed handling for security, persistence ambiguity, and hard budget;
- generation-scoped repeat escalation and strategy switching;
- stateful controller cursor checkpoint/restore;
- Stage 03 receipt semantics preserved for non-idempotent effects.

Final candidate `v0.6.0-rc6` passed **94 tests with 5 hosted-environment namespace skips** plus all Stage 03, Stage 04, and Stage 05 direct probes. Unsafe automatic retries, verified-fact recovery mutations, ambiguous external executions, lost scheduled recovery transitions, and hard-budget step overshoot were all 0 in the declared test matrices.

## Guarantee boundaries

### Stage 02
Production isolation requires a successful live `runtime_probe`. Hosted-runner skips do not count as production isolation proof.

### Stage 03
Non-idempotent effects are at-most-once automatically executed: COMMITTED receipts deduplicate; PREPARED-only receipts halt/fail closed. No universal exactly-once claim.

### Stage 04
Generic structured verification does not solve natural-language truth. Domain-semantic facts require domain-specific verifier coverage.

### Stage 05
Recovery guarantees durable **control transitions**, not guaranteed semantic repair by an LLM and not transactional rollback of arbitrary external systems.

## Development rule

Use `research/verified-state-stage03` as the single continuing research branch. Do not create a branch per Stage. Every completed Stage must include code, tests/probes, machine-readable evidence, implementation/review/exit Markdown reports, and full regression.

## Next work

Stage 06 must freeze a **Progress Contract** before implementation. The next problem is detecting meaningful progress versus repeated/no-progress behavior without trusting Actor self-reporting and without weakening Stage 01–05 gates.
