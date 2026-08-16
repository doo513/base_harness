# Verified-State Harness

This research branch is the standalone implementation of the new harness architecture. The repository's `main` branch remains the preserved legacy **Base Harness** and is not modified by this development line.

## Project hypothesis

A general-purpose agent harness should not trust an Actor's narrative of progress. Goal contracts, evidence, verification, isolation, persistence, recovery, and completion should be externalized into deterministic or runtime-enforced mechanisms.

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
Domain VerificationContract
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
| 04 | Semantic verification | PASS / EXITED |
| 05 | Failure recovery | NEXT / NOT STARTED |

Current package version: **v0.5.0**.

## Stage 04 result

Stage 04 moves the kernel from “a verifier returned true” to an explicit verification contract:

- verifier result cannot self-inflate its configured strength;
- result-supplied coverage cannot invent semantic authority;
- Domain Profiles declare required verification coverage and strength;
- semantic evidence is content-address integrity checked when read;
- the generic execution verifier only proves narrow JSON artifact assertions;
- generic assertions can only commit under `artifact_assertion.*`;
- arbitrary domain-semantic keys require domain-specific verifier code;
- structural/logical support is represented as `SUPPORTED`, not semantic execution truth;
- verification contract/verifier metadata are part of the reproducibility fingerprint;
- resume fails closed when persisted and executing harness versions differ.

Promotion candidate `v0.5.0-rc3` passed 69 tests with 5 environment-dependent skips. The Stage 04 adversarial matrix produced FP=0/FN=0 and blocked level inflation, artifact tamper, and semantic-key masquerading.

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

## Guarantee boundaries

### Stage 02

`LinuxNamespaceSandboxBackend` is considered production-isolated only when its live runtime attestation succeeds. Unsupported hosts fail closed.

### Stage 03

Non-idempotent side effects use durable PREPARED/COMMITTED receipts. COMMITTED operations are deduplicated; PREPARED-only operations are ambiguous and halt/fail closed. This is an **at-most-once automatic execution** guarantee, not universal exactly-once semantics.

### Stage 04

The generic verifier does **not** solve natural-language truth. It verifies only explicit structured propositions over integrity-checked artifacts. Domain-semantic facts require Domain Profile verifiers with declared coverage satisfying the profile's `VerificationContract`.

## Next work

Stage 05 is **Failure Recovery**. The current `FailureRouter` recommends actions but does not yet make recovery a first-class, kernel-owned state transition. Stage 05 must freeze that transition contract before implementation and prove that recovery cannot bypass truth, isolation, verification, persistence, or completion gates.

See `docs/handoff/README_HANDOFF.md` and `docs/handoff/02_CURRENT_STATUS.md` before continuing implementation.
