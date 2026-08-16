# 02 — Current Status

## Stage 00 — Research Contract

Status: **COMPLETE**.

## Stage 01 — Truth / Execution Hardening

Status: **COMPLETE** for the scoped P0 defects.

## Stage 02 — Capability Isolation + Sealed Oracle

Status: **PASS / EXITED** for `LinuxNamespaceSandboxBackend` when live `runtime_probe` succeeds.

Stage 02 production guarantee remains environment-dependent and is not redefined by later hosted-CI skips.

## Stage 03 — Persistence / Resume / Reproducibility

Status: **PASS / EXITED**.  
Version: `v0.4.0`.

Core guarantee:

```text
COMMITTED non-idempotent receipt -> deduplicate
PREPARED-only receipt            -> ambiguous, halt/fail closed
```

This is at-most-once automatic execution, not universal exactly-once semantics.

## Stage 04 — Semantic Verification

Status: **PASS / EXITED**.  
Version: `v0.5.0`.

Implemented:

- explicit Domain `VerificationContract`;
- verifier level/coverage normalization;
- evidence/strength/coverage requirements;
- read-time content-address artifact integrity verification;
- narrow `StructuredArtifactAssertionVerifier`;
- generic assertion namespace `artifact_assertion.*`;
- `SUPPORTED` authority for structural/logical facts;
- verification contract/verifier metadata in reproducibility fingerprint;
- fail-closed cross-version resume guard.

Promotion candidate evidence:

```text
candidate                v0.5.0-rc3
candidate commit          11e707cf04ea76f20a9b810d159a58fe1c1e2430
GitHub Actions run        31934328945
full pytest               69 passed / 5 skipped
semantic matrix           8 / 8 PASS
false positives           0
false negatives           0
level inflation           BLOCKED
artifact tamper           BLOCKED
semantic-key masquerade   BLOCKED
version drift resume      BLOCKED
```

Important scope: generic natural-language truth is not solved. Domain-semantic facts require Domain Profile verifier coverage.

## Current unresolved work

The next allowed Stage is **Stage 05 — Failure Recovery**.

The current `FailureRouter` recommends `REPAIR`, `OBSERVE`, `ROLLBACK`, `REPLAN`, `SWITCH_STRATEGY`, etc., but recovery is not yet a first-class durable kernel transition. Stage 05 must freeze that transition contract before implementation.
