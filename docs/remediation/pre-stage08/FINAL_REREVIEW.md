# Pre-Stage08 Remediation — FINAL REREVIEW

Candidate: **v0.8.1rc2**  
Scope: P0-1 verified-read single-buffer integrity hardening.

## Logic review

### L1 — Can bytes different from the bytes hashed be returned by `verified_read_bytes()`?

**PASS.** The digest is computed over the same `raw` bytes object returned by the method.

### L2 — Can pathname replacement after verification substitute the return value?

**PASS in the tested race.** The pathname is replaced after the first read chunk; the existing FD continues reading the original inode. The returned bytes match the original digest. A subsequent new logical read opens the replacement and rejects its mismatched digest.

### L3 — Is a resolved path itself called verified?

**PASS.** Path resolution is explicitly confinement-only. Internal semantic consumers use verified bytes.

### L4 — Does the remediation weaken SHA-256 verification to reduce cost?

**PASS.** One full SHA-256 verification remains on every critical verified read.

## Implementation review

### I1 — Final-component symlink substitution

**PASS on supported platforms.** `O_NOFOLLOW` is included when available and the opened object must be a regular file by `fstat`.

### I2 — Missing/malformed/path escaping refs

**PASS.** Dedicated tests/probe fail closed.

### I3 — Stage-04 consumer re-open

**PASS.** Internal evidence/claim/assertion verifiers parse the verified byte buffer rather than reopen a path after authorization.

### I4 — Stage-06 consumer re-open

**PASS.** Progress fingerprints the verified byte buffer.

### I5 — Stage-03 persistence regression

**FOUND / FIXED.** During remediation, a manual reconstruction of `storage.py` temporarily changed manifest/checkpoint envelope schema. Full regression caught two failures. The exact baseline file was refetched from commit `0d396d37...`; RunManifestStore, CheckpointStore, and ReceiptStore semantics were restored and only ArtifactStore hardening was retained.

### I6 — Accidental placeholder write

**FOUND / FIXED / AUDIT PRESERVED.** A transient commit wrote `PLACEHOLDER` to `storage.py`. It was immediately corrected. No force rewrite was used to erase the incident.

## Structural review

### S1 — Inspection/consumption identity

**PASS.** The artifact content object authorized by the digest is the byte buffer returned to the caller.

### S2 — Central authority boundary

**PASS.** ArtifactStore now owns the verified-read primitive. Stage-04 and Stage-06 use it.

### S3 — Compatibility helper risk

`_verified_artifact_path()` remains for compatibility. It performs a check before returning a path but cannot guarantee future bytes after return. Internal security/semantic consumers do not use it as an authorization object. Future code review should reject new trust-sensitive consumers of this helper.

Severity: **documented compatibility boundary**, not a blocker for P0-1.

### S4 — Artifact-store attacker model

Content-address SHA-256 detects byte drift relative to the persisted ref. It is not cryptographic authentication against an attacker who can rewrite both trusted references/state and the artifact store. Stage-02 filesystem isolation remains necessary to keep Actor access away from the private run directory.

## Cost review

The corrected path reduces artifact content reads from `2N` to `N` for the flawed double-read algorithm while preserving one SHA-256 pass. Production prompt tokens, checkpoint schema, and event-log size are unchanged.

## Validation status before release bump

Corrected candidate run `31947812417`:

```text
pytest                         131 passed / 5 skipped
Stage03 resume                 PASS 4/4
Stage04 semantic               PASS 8/8, FP=0/FN=0
Stage05                        PASS
Stage06                        PASS
Stage07                        PASS
Stage08 integrity race probe   PASS 6/6
unverified return buffers      0
```

## Remaining remediation blockers

P0-1 completion does **not** authorize Stage-08 feature implementation yet. The remediation plan next requires:

1. Stage-02 nested read-only submount runtime reproduction;
2. if reproduced, recursive RO enforcement or fail-closed topology rejection;
3. Tool execution path ↔ attested backend binding;
4. release provenance hardening;
5. claim-class verification;
6. semantic progress;
7. trusted context growth control;
8. retrieval request model and integration.

## Candidate judgment

```text
P0-1 unresolved Critical: 0
P0-1 unresolved High:     0
prior-stage regression:   0 after correction
verified-read TOCTOU:     blocked in direct race probe
```

**Recommendation:** bump to `v0.8.1`, rerun the complete CI on the exact release snapshot, and only then freeze P0-1.
