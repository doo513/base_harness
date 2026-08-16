# Stage 04 Implementation Report — Semantic Verification

**Release:** `v0.5.0`  
**Stage:** 04  
**Decision:** PASS / EXITED  
**Development branch:** `research/verified-state-stage03` (single continuing research branch)

## 1. Purpose

Stage 04 addressed a specific gap left after Truth Authority, isolation, and persistence were hardened:

```text
“only verifier may commit”
        ≠
“the verifier's evidence actually establishes this class of claim”
```

The implementation goal was therefore not to add many verifiers. It was to make semantic authority explicit and kernel-enforced.

## 2. Entry-state findings

The pre-implementation review found these defects:

1. `VerificationResult.level` could be used as if it were trusted verifier strength. A buggy verifier could report a stronger level than its configured implementation level.
2. Result-provided semantic coverage had no independent authority boundary.
3. `SoftwareProfile` required `EXECUTION` while its old chain only reached `LOGICAL`, so ordinary claim verification was structurally incapable of satisfying its declared minimum.
4. Stored artifact existence proved storage/relevance at best, not semantic truth.
5. Structural/logical verification was mapped to `TRUSTED_TOOL`, overstating semantic authority.
6. Verification requirements were not a first-class Domain Profile contract.

## 3. Implemented model

### 3.1 VerificationContract

A Domain Profile now supplies a `VerificationContract` containing:

- minimum verification level;
- named required coverage;
- per-requirement minimum level;
- optional evidence requirement;
- optional confidence threshold.

The kernel assesses the entire contract before committing a hypothesis to trusted facts.

### 3.2 Trusted verifier metadata

`VerifierChain` normalizes result metadata from configured verifier objects:

```text
configured verifier level  → authoritative
configured verifier covers → authoritative
result-reported escalation → rejected
result-supplied coverage    → ignored/replaced
```

A verifier result that reports a different level from the configured implementation fails closed.

### 3.3 Evidence integrity

Artifacts produced by `ArtifactStore` are content-addressed. Stage 04 adds read-time verification of the SHA-256 embedded in an artifact reference before semantic verification consumes its bytes.

This prevents a stale artifact reference from silently authorizing modified content.

### 3.4 Generic structured semantic primitive

The generic execution verifier intentionally supports only a narrow proposition:

```json
{
  "kind": "artifact_json_assertion",
  "path": ["output", "returncode"],
  "operator": "eq",
  "expected": 0
}
```

It proves only equality at an explicit JSON path in one integrity-verified evidence artifact.

It does not infer that an arbitrary natural-language statement is true.

### 3.5 Claim namespace boundary

Generic artifact assertions can only promote facts under:

```text
artifact_assertion.*
```

For example, a generic `returncode == 0` assertion cannot be renamed to `security.sql_injection_success` and thereby acquire domain meaning. Such a domain-semantic key requires a dedicated Domain Profile verifier whose declared coverage satisfies the profile contract.

### 3.6 Authority correction

Structural/logical acceptance now maps to `Authority.SUPPORTED`. Execution-level evidence maps to `Authority.ENVIRONMENT`; external oracle evidence maps to `Authority.EXTERNAL_ORACLE`.

This separates “well-supported record” from “execution-observed fact”.

### 3.7 Reproducibility integration

The Stage 03 manifest fingerprint is extended with:

- serialized `VerificationContract`;
- verifier names/classes;
- declared levels;
- declared coverage;
- verifier source hashes.

Resume also rejects a persisted run when `harness_version` differs from the executing harness version.

## 4. Candidate history and discovered errors

### rc1 — failed

The first Stage 04 implementation accidentally replaced the completed Stage 03 `runtime_persistence.py` with an incomplete working copy. GitHub CI exposed this immediately: 12 regression tests failed.

Observed failure class included missing runtime metadata handling and incompatible receipt calls. The candidate was not promoted.

Correction:

- restore the exact Stage 03 persistence implementation;
- avoid rewriting persistence for Stage 04;
- extend the Stage 03 config fingerprint through a minimal runtime override only.

### rc2 — semantic/evidence hardening

After rc1 was repaired, CI passed. A second adversarial review nevertheless found two semantic false-positive paths:

1. content-address artifact references were not rehashed at verifier read time;
2. a generic structured assertion could be stored under an arbitrary semantic claim key.

rc2 added read-time artifact integrity verification and the `artifact_assertion.*` namespace boundary.

### rc3 — reproducibility boundary

A final review found that `run_manifest.json` recorded `harness_version` but resume did not directly compare it to the running version. rc3 added a fail-closed version-drift guard and regression test.

## 5. Methodology

The Stage followed this order:

```text
entry-state code review
→ freeze semantic contract
→ implement minimum kernel mechanism
→ adversarial unit tests
→ full CI
→ inspect failure logs
→ restore earlier-stage invariant
→ full CI
→ second adversarial review
→ evidence-integrity/namespace hardening
→ full CI
→ final reproducibility review
→ version-drift hardening
→ final candidate CI
→ exit decision
```

A passing candidate was deliberately re-reviewed before promotion; rc2 passed CI but was still not treated as final because two additional false-positive paths were found by manual structural review.

## 6. Final candidate evidence

Promotion candidate: `v0.5.0-rc3`  
Candidate commit: `11e707cf04ea76f20a9b810d159a58fe1c1e2430`  
GitHub Actions run: `31934328945`

```text
compileall                       PASS
full pytest                      69 passed / 5 skipped
Stage 04 semantic matrix         8 / 8 PASS
semantic false positives         0
semantic false negatives         0
level-inflation attempt          BLOCKED
artifact-content tamper          BLOCKED
semantic-key masquerade          BLOCKED
cross-version resume drift       BLOCKED (regression test)
```

The five skipped tests are live Linux namespace tests that skip when the hosted runner cannot produce a `runtime_probe` production attestation. Stage 04 did not change the Stage 02 namespace implementation; direct Stage 02 production evidence remains the authority for that environment-dependent boundary.

## 7. Non-claims / remaining limitations

Stage 04 does **not** establish:

- universal natural-language truth verification;
- correctness of arbitrary third-party verifier code;
- independence of every in-process verifier from the kernel TCB;
- domain-semantic meaning from generic execution assertions;
- benchmark superiority over external harnesses.

Trusted verifier implementation code remains part of the TCB. Domain-specific semantics require Domain Profile verifier implementations and their own adversarial tests.

## 8. Exit

The frozen Stage 04 criteria are satisfied. Stage 04 is **PASS / EXITED** and `v0.5.0` is promoted.
