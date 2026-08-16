# 02 — Current Status

## Stage 00 — Research Contract

Status: **COMPLETE**.

## Stage 01 — Truth / Execution Hardening

Status: **COMPLETE** for the scoped P0 defects.

## Stage 02 — Capability Isolation + Sealed Oracle

Status: **PASS / EXITED** for `LinuxNamespaceSandboxBackend` when live `runtime_probe` succeeds.

Stage 03 changes were regression-tested against the real Stage 02 attack probe:

```text
required attacks      12 / 12 PASS
defense-in-depth       4 / 4 PASS
runtime attestation   PASS
workspace control     PASS
```

## Stage 03 — Persistence / Resume / Reproducibility

Status: **PASS / EXITED**.

Version: `v0.4.0`.

Implemented and directly verified:

- integrity-bound `run_manifest.json`
- hash-chained `events.jsonl`
- canonical `state.snapshot` replay
- atomic checkpoint envelope with event anchor
- event-ahead checkpoint recovery
- public `HarnessRuntime.resume(...)`
- CLI `--resume`
- cumulative wall-budget continuity
- non-idempotent PREPARED/COMMITTED receipts
- committed-action deduplication
- PREPARED-only ambiguity fail-closed behavior
- task/model/profile/verifier/tool/security/budget/oracle provenance fingerprinting
- dirty run-directory fail-closed behavior

Final evidence:

```text
Stage 03 tests          12 passed
full pytest             59 passed
direct Stage 03 probe    4 / 4 PASS
duplicate external       0
compileall               PASS
Stage 02 regression      PASS
```

Important guarantee boundary:

```text
non-idempotent tools => at-most-once automatic execution
PREPARED-only receipt => ambiguous, therefore halt/fail closed
```

The project does not claim universal exactly-once semantics for arbitrary external systems.

## Current unresolved work

The next allowed stage is **Stage 04 — Semantic Verification (`v0.5.0`)**.

Before implementation, freeze the Stage 04 verification contract and adversarial false-positive/false-negative test matrix. Do not weaken Stage 01–03 gates to make semantic verification easier.
