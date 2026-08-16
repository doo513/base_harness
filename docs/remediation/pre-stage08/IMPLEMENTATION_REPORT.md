# Pre-Stage08 Remediation — IMPLEMENTATION REPORT

Status: **P0-1 implemented / release validation pending**  
Target: `v0.8.1`  
Scope: verified artifact read integrity only; Stage-08 retrieval feature remains blocked.

## 1. Objective

Apply the remediation invariant:

> The object inspected must be structurally identical to the object executed, consumed, or committed.

For artifact reads, a digest check over bytes A must never authorize later bytes B obtained by reopening a pathname.

## 2. Finding classification

### R08-P0-001

- claim: the first centralized verified-read candidate contained a double-read TOCTOU
- class: **confirmed_defect**
- evidence level: direct code + adversarial test
- before: verify bytes from `path.read_bytes()`, return bytes from another `path.read_bytes()`
- after: open once, `fstat`, read one logical buffer, hash that buffer, return the same buffer

### R08-P0-002

- claim: Stage-04 and Stage-06 artifact integrity logic was duplicated
- class: **confirmed_defect / enforcement fragmentation**
- evidence level: direct code
- after: both semantic verification and progress consume `ArtifactStore` verified bytes

## 3. Implementation

### ArtifactStore boundary

`resolve_ref_path()` is now explicitly a path-confinement helper only. It parses the opaque artifact token, validates the content-address digest syntax, constrains it to the artifact root, and returns a pathname without claiming that future reads from that pathname are verified.

`verified_read_bytes_from_root()` performs the actual integrity operation:

```text
open artifact-root directory FD
-> open artifact token relative to dirfd
-> O_NOFOLLOW where available
-> fstat and require regular file
-> os.read loop over one opened FD
-> SHA-256 over the resulting buffer
-> compare to artifact-ref digest
-> return that same buffer
```

`verified_read_text()` and `verified_read_json()` derive only from the verified byte buffer.

### Stage-04 consumer migration

The following paths consume verified content buffers directly:

- `EvidenceRefVerifier`
- `ClaimBoundEvidenceVerifier`
- `StructuredArtifactAssertionVerifier`

A compatibility `_verified_artifact_path()` remains, but internal semantic verifiers do not rely on a future-read guarantee from it.

### Stage-06 consumer migration

`RuntimeProgressMixin._verified_observation_fingerprint()` obtains bytes through `self.artifacts.verified_read_bytes(ref)` and parses/fingerprints that exact content.

## 4. Adversarial race test

A deterministic race fixture creates a >1 MiB artifact so `os.read()` executes multiple chunks. After the first successful read, the pathname is atomically replaced with a different file.

Expected behavior:

```text
already-open original inode -> complete read -> original digest PASS -> original buffer returned
new later logical read      -> replacement bytes -> digest mismatch -> BLOCK
```

This directly detects re-opening between verification and consumption.

## 5. Regression incident during remediation

Two implementation-process errors occurred and are retained in Git history rather than hidden:

1. a transient update accidentally wrote `PLACEHOLDER` to `storage.py`; it was immediately restored;
2. the first manual restoration reconstructed the Stage-03 manifest/checkpoint envelope incorrectly, causing two regression failures (`body` envelope missing).

The second error produced CI result:

```text
129 passed / 5 skipped / 2 failed
```

The correction fetched the exact baseline `storage.py` from commit `0d396d37...`, restored the original RunManifestStore / CheckpointStore / ReceiptStore semantics, and reapplied only the ArtifactStore hardening.

Corrected candidate CI then passed:

```text
131 passed / 5 skipped
Stage 03 resume probe        PASS 4/4, duplicate external actions 0
Stage 04 semantic probe      PASS 8/8, FP=0, FN=0
Stage 05 probes              PASS
Stage 06 probes              PASS
Stage 07 probes              PASS
Stage 08 integrity probe     PASS 6/6
unverified return buffers    0
```

## 6. Methodology

The remediation deliberately used:

1. source-level defect confirmation;
2. an adversarial race that mutates the pathname after the first content read;
3. full regression rather than targeted-test-only acceptance;
4. prior Stage direct probes;
5. explicit documentation of implementation mistakes and corrective commits;
6. a separate cost probe so correctness and performance claims are not conflated.

## 7. Non-goals

This hardening does not yet implement:

- Stage-08 retrieval/memory runtime;
- Stage-02 recursive mount remediation;
- ToolSpec/backend binding;
- stronger release provenance;
- claim-class verification registry;
- semantic progress;
- trusted-context hard cap.

Those remain subsequent remediation gates.
