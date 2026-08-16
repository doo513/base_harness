# Verified-State Harness

This branch is a standalone implementation of the new harness architecture. The repository's `main` branch remains the preserved legacy **Base Harness**; this research branch intentionally does not carry the old root implementation forward.

## Project hypothesis

A general-purpose agent harness should not trust an Actor's narrative of progress. It should externalize goal contracts, evidence, verification, isolation, persistence, and completion into deterministic/runtime-enforced mechanisms.

Core invariant:

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success.**

## Architecture

```text
Goal / Requirement Contract
        ↓
Observation / Evidence Gate
        ↓
Trusted Working State
        ↓
Actor Decision
        ↓
Capability / Permission / Isolation Gate
        ↓
Tool Runtime
        ↓
Evidence / Hypothesis
        ↓
Verifier Chain
        ↓
Kernel-owned State Commit

Completion request
        ↓
Sealed Completion Oracle
        ↓
Kernel accepts / rejects

Persistence plane
  Manifest → hash-chained events → atomic checkpoint
           → side-effect receipts → deterministic replay

+ Domain Profile
  tools() · state_schema() · failure_taxonomy()
  memory_policy() · verification_contract() · completion_oracle()
```

## Current Stage status

| Stage | Scope | Status |
|---|---|---|
| 00 | Research / contracts | COMPLETE |
| 01 | Truth + execution integrity | COMPLETE |
| 02 | Capability isolation + sealed oracle | PASS / EXITED |
| 03 | Persistence + resume + reproducibility | PASS / EXITED |
| 04 | Semantic verification | NEXT / NOT STARTED |

Current package version: **v0.4.0**.

Stage 03 evidence includes 59 passing regression tests, direct forced-termination/resume probes, duplicate external action count 0, deterministic replay hash checks, checkpoint corruption fail-closed behavior, and a re-run of the Stage 02 filesystem/network attack probe.

## Repository layout

```text
src/                harness implementation
tests/              regression + Stage adversarial tests
scripts/            direct runtime/attack probes
evidence/           machine-readable execution evidence
docs/               implementation reports and research records
docs/stages/        Stage-by-Stage status and exit reports
docs/handoff/       continuation material for other agents
docs/archive/       historical artifact identity/index material
```

## Development rule

This branch is the continuing development line. **Do not create a branch per Stage.** Each Stage is represented by code, version, evidence, and Markdown reports in this branch. `main` remains untouched unless the user explicitly requests otherwise.

## Stage 02 guarantee boundary

The production sandbox is `LinuxNamespaceSandboxBackend` and is accepted only when its live runtime attestation succeeds. It uses Linux user/mount/PID/network namespaces, chrooted mount views, read-only verifier/oracle views, sealed oracle assets, capability dropping, environment sanitization, and direct attack probes. Unsupported hosts fail closed.

## Stage 03 guarantee boundary

Non-idempotent side effects use durable PREPARED/COMMITTED receipts. A COMMITTED operation is not automatically replayed. A PREPARED-only receipt is ambiguous after a crash and therefore halts/fails closed. This is an **at-most-once automatic execution** guarantee; the project does not claim universal exactly-once semantics for arbitrary external systems.

## Next work

Stage 04 must begin by freezing the semantic verification contract and adversarial false-positive/false-negative matrix. A verifier existing or returning `True` is not, by itself, evidence of semantic correctness.

See `docs/handoff/README_HANDOFF.md` and `docs/handoff/02_CURRENT_STATUS.md` before continuing implementation.
