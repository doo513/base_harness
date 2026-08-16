# Stage 08 — Retrieval / Memory Gateway Preflight Re-review

Status: **ENTRY REVIEW COMPLETE — PREREQUISITE HARDENING IN VALIDATION**  
Baseline: `v0.8.0` / branch `research/verified-state-stage03`  
Candidate: `v0.8.1rc2`

## Purpose

Stage 08 will add a retrieval/memory admission path only after the existing truth, persistence, recovery, progress, and context gates can safely carry retrieved material. This preflight deliberately does not select a vector database, embedding model, RAG framework, or autonomous memory writer.

## Classification

- **A — Confirmed code defect**
- **B — Security hypothesis requiring runtime reproduction**
- **C — Research / coverage gap**

## Findings

### PF01 — Existing `MemoryStore.search()` mutates retrieval state
Class: **A**. Severity: **High for Stage-08 use**.

`search()` increments `recall_count` on every returned item. The same query is therefore not a pure read. The prototype is not admissible as a Stage-08 gateway.

### PF02 — Existing MemoryItem authority is self-describing free text
Class: **A**. Severity: **High for Stage-08 use**.

`MemoryItem.authority` is arbitrary caller text and `add()` can replace items. Stage-08 admitted items must have fixed `untrusted_retrieval` trust and `instruction_authority=none`.

### PF03 — Memory overwrite / supersession is not controlled
Class: **A**. Severity: **High for Stage-08 use**.

Content identity must be immutable; source updates require new identities and explicit Kernel-owned supersession.

### PF04 — Retrieval tie ordering is not contractually deterministic
Class: **A/C**. Severity: **Medium/High**.

Equal-score ordering may depend on insertion order. Stage-08 requires a stable total tie-break.

### PF05 — No retrieval/memory provenance exists in the run manifest
Class: **C**. Severity: **High before Stage-08 implementation**.

Retrieval policy/provider/index revision must be fingerprinted before feature implementation.

### PF06 — DomainProfile has no memory/retrieval policy extension
Class: **C**. Severity: **Medium**.

Initial Stage-08 policy remains Kernel/runtime-owned rather than an unconstrained profile callback.

### PF07 — `OptionalGateway.retriever` is untyped
Class: **A/C**. Severity: **Medium/High**.

Do not wire it directly into Context Governor; define a typed gateway/request/admission contract first.

### PF08 — Artifact content verification was duplicated
Class: **A**. Severity: **High prerequisite defect**.

Stage 04 and Stage 06 implemented separate artifact verification semantics. Stage 08 would create a third reader if this were left unresolved.

### PF08b — Initial centralized candidate had verified-read TOCTOU
Class: **A — Confirmed code defect in an unpromoted candidate**. Severity: **Critical for the verified-read guarantee**.

The first draft was:

```text
read A -> hash A -> return path -> read B -> caller consumes B
```

This violates the remediation invariant that the inspected object and consumed object must be the same.

The draft commit was never accepted as a release. `v0.8.1rc2` changes the boundary to:

```text
open artifact FD relative to artifact-root FD
-> reject final-component symlink where supported
-> fstat regular-file check
-> read one logical byte buffer
-> SHA-256 that exact buffer
-> return that same buffer
```

`resolve_ref_path()` is explicitly only path confinement/existence. It is not a verified-content API.

Consumer migration:

- Stage-04 `EvidenceRefVerifier` hashes the returned verified buffer directly;
- Stage-04 `ClaimBoundEvidenceVerifier` parses JSON from the returned verified buffer;
- Stage-04 `StructuredArtifactAssertionVerifier` evaluates the assertion over JSON parsed from the returned verified buffer;
- Stage-06 progress fingerprints JSON parsed from `ArtifactStore.verified_read_bytes()`;
- the legacy `_verified_artifact_path()` helper remains compatibility-only and is explicitly not used by internal semantic consumers.

Adversarial validation includes a pathname replacement after the first `os.read()`. Because the verified reader continues consuming the already-open inode and returns the same buffer, replacement cannot substitute caller-visible bytes. A later new logical read opens the changed pathname and must fail the digest check.

### PF09 — Retrieval must not reuse successful tool observations as progress evidence
Class: **C / integration hazard**. Severity: **High design constraint**.

Retrieval remains a distinct evidence/context channel and is not Stage-06 progress by admission alone.

### PF10 — Actor currently has no direct memory-write Decision
Class: **positive baseline invariant**.

This is preserved.

### PF11 — Failure taxonomy has no retrieval-specific failure kind
Class: **C**. Severity: **Non-blocking if mapped consistently**.

Existing typed failures remain sufficient unless implementation proves otherwise.

### PF12 — HarnessState has no durable retrieval ledger
Class: **C / missing Stage-08 structure**. Severity: **High before Stage-08 implementation**.

Stage 08 must add a hash-chained admitted retrieval snapshot/ledger before model-visible retrieval is implemented.

## Entry decision

Stage-08 feature implementation remains **BLOCKED** until `v0.8.1rc2` passes:

```text
targeted unit + adversarial tests
full pytest regression
Stage 03-07 direct probes
Stage 08 artifact-integrity probe
compile/static check
```

After that, the next remediation gate is Stage-02 nested-submount runtime reproduction. The Stage-08 feature itself remains after the remediation sequence.

## Cost expectation for P0-1

The corrected critical read performs one logical content read and one SHA-256 over the exact returned bytes. It removes the draft double-read TOCTOU and avoids the extra content read that created it. Measured before/after I/O and wall-time data will be recorded in the remediation cost report; no inode/mtime cache may replace a critical integrity revalidation.
