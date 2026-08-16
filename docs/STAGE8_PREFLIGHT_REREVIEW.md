# Stage 08 — Retrieval / Memory Gateway Preflight Re-review

Status: **ENTRY REVIEW COMPLETE — PREREQUISITE HARDENING REQUIRED**  
Baseline: `v0.8.0` / branch `research/verified-state-stage03`

## Purpose

Stage 08 will add a retrieval/memory admission path only after the existing truth, persistence, recovery, progress, and context gates can safely carry retrieved material. This preflight deliberately does not select a vector database, embedding model, RAG framework, or autonomous memory writer.

## Baseline inspected

- `src/harness/core/context.py`
- `src/harness/core/storage.py`
- `src/harness/core/verification.py`
- `src/harness/core/runtime_progress.py`
- `src/harness/core/state.py`
- `src/harness/core/memory.py`
- `src/harness/core/extensions.py`
- `src/harness/core/runtime_persistence.py`
- `src/harness/core/runtime.py`
- `src/harness/core/controller.py`
- `src/harness/core/failures.py`
- `src/harness/profiles/base.py`

## Finding classes

All findings in this remediation use one of:

- **A — Confirmed code defect**
- **B — Security hypothesis requiring runtime reproduction**
- **C — Research / coverage gap**

## Findings

### PF01 — Existing `MemoryStore.search()` mutates retrieval state
Class: **A**. Severity: **High for Stage-08 use**.

`search()` increments `recall_count` on every returned item. The same query is therefore not a pure read. A retrieval operation can change persisted/observable memory merely by being evaluated, which complicates deterministic replay and crash/resume equivalence.

**Decision:** existing `MemoryStore` is legacy/prototype only and is not an admissible Stage-08 gateway implementation.

### PF02 — Existing MemoryItem authority is self-describing free text
Class: **A**. Severity: **High for Stage-08 use**.

`MemoryItem.authority` is an arbitrary string and `MemoryStore.add()` accepts/replaces items without a kernel admission rule. A caller could label retrieved text as trusted/verified without Stage-04 verification.

**Decision:** Stage-08 admitted items have fixed untrusted retrieval authority. Epistemic promotion is impossible inside the retrieval store.

### PF03 — Memory overwrite / supersession is not controlled
Class: **A**. Severity: **High for Stage-08 use**.

`MemoryStore.add()` overwrites by id. There is no immutable content identity, source revision, supersession relation, conflict rule, or audit transition.

**Decision:** content identity and source identity are separate. Replacing an existing id with different bytes is forbidden; supersession is an explicit kernel-owned relation.

### PF04 — Retrieval tie ordering is not contractually deterministic
Class: **A/C**. Severity: **Medium/High**.

The prototype sorts only by score descending. Equal scores fall back to container insertion order, which is not an acceptable cross-reconstruction/index contract.

**Decision:** every retrieval result order must have a stable total tie-break independent of insertion order.

### PF05 — No retrieval/memory provenance exists in the run manifest
Class: **C**. Severity: **High before Stage-08 implementation**.

`HarnessRuntime._config_descriptor()` fingerprints goal/profile/controller/security/tools/oracle/recovery/progress/context, but there is no retrieval policy/index/source descriptor because no governed retrieval subsystem exists.

**Decision:** Stage-08 gateway policy + index/source snapshot identity + implementation descriptor are part of the config hash. Drift on resume fails closed.

### PF06 — DomainProfile has no memory/retrieval policy extension
Class: **C**. Severity: **Medium**.

The current `DomainProfile` exposes tools/verifiers/verification contract/oracle only. Earlier planning language referring to a memory-policy placeholder was inaccurate.

**Decision:** the initial Stage-08 policy belongs to the kernel/runtime configuration, not an unconstrained DomainProfile callback. A future profile extension must return a typed descriptor if introduced.

### PF07 — `OptionalGateway.retriever` is untyped
Class: **A/C**. Severity: **Medium/High**.

`OptionalGateway.retriever: object | None` has no source/provenance/trust/determinism contract and is not currently wired into the governed runtime.

**Decision:** do not wire this field directly into Context Governor. Stage-08 defines a typed gateway protocol first.

### PF08 — Artifact content verification is duplicated rather than centralized
Class: **A**. Severity: **High prerequisite defect**.

Stage 04 verification contains `_verified_artifact_path()` while Stage 06 progress independently parses the digest, reads bytes, hashes them, and validates JSON. `ArtifactStore` itself exposes path resolution/existence/write but no authoritative verified-read primitive.

This duplication is dangerous for Stage 08: a third retrieval reader could implement subtly different integrity semantics.

**Required preflight hardening:** centralize content-address verification in `ArtifactStore` and make Stage 04/06 delegate to it before Stage-08 retrieval reads are implemented.

### PF08b — Initial centralized verified-read candidate had a double-read TOCTOU
Class: **A — Confirmed code defect in the unpromoted candidate**. Severity: **Critical for the verified-read guarantee**.

The first `v0.8.1rc1` draft verified bytes inside path resolution and then reopened/read the same path to return bytes to the caller:

```text
read A -> hash A -> path returned -> read B -> caller consumes B
```

A replacement between the two reads could make the caller consume bytes that were never hashed. This violates the top-level remediation invariant: the object inspected must be the object consumed.

**Decision:** the draft commit is not promoted to the research branch. The replacement primitive must perform one logical content read, hash that exact buffer, and return that same buffer. Path resolution is confinement/existence only and must never be described as content verification.

Required tests include a deterministic swap-after-first-read simulation proving that there is no second content read to substitute.

### PF09 — Retrieval must not reuse successful tool observations as progress evidence
Class: **C / integration hazard**. Severity: **High design constraint**.

Stage 06 intentionally counts novel integrity-checked successful observation content as progress. If retrieval is modeled as an ordinary successful tool observation, merely reading a new memory item could reset no-progress control even though the external task state did not advance.

**Decision:** retrieval candidates are a distinct context/evidence channel. Retrieval itself is not Stage-06 progress. Only later verified fact changes or separately qualifying task observations count under the existing Progress Contract.

### PF10 — Actor currently has no direct memory-write Decision
Class: **positive baseline invariant**.

Allowed Decisions are propose/verify/tool/refute/complete. No direct memory mutation exists.

**Decision:** Stage 08 does not add an Actor-owned trusted `memory_write` decision. Any memory admission request must be mediated by a kernel-owned API/policy and remains untrusted.

### PF11 — Failure taxonomy has no retrieval-specific failure kind
Class: **C**. Severity: **Non-blocking if contractually mapped**.

Existing typed failures are sufficient if mapped consistently:
- corruption/integrity/provenance conflict -> `PERSISTENCE_ERROR` -> terminal fail closed;
- unavailable optional source -> `ENV_ERROR`/`MISSING_INFO` according to policy, never fabricate fallback;
- implementation violation -> `IMPLEMENTATION_ERROR`.

A new failure enum is unnecessary unless implementation proves these distinctions insufficient.

### PF12 — HarnessState has no durable retrieval ledger
Class: **C / missing Stage-08 structure**. Severity: **High before Stage-08 implementation**.

`HarnessState` contains facts, hypotheses, observations, evidence refs and control state but no admitted retrieval snapshot/history. Context projection therefore has no durable, replayable retrieval input.

**Decision:** Stage 08 must add a small kernel-owned retrieval admission state (or an equivalently hash-chained durable ledger) rather than deriving model context from a mutable external index at every Actor call.

## Entry decision

Stage 08 feature implementation is **BLOCKED** until PF08/PF08b are closed and their full Stage 03–07 regression passes.

The Retrieval / Memory Admission Contract remains frozen because the artifact-read hardening changes only the shared integrity primitive, not retrieval semantics.

## Corrected preflight hardening plan

`v0.8.1` candidate:

```text
ArtifactStore path confinement / content-address parser
-> verified_read_bytes(ref): open/read once -> hash exact bytes -> return same bytes
-> verified_read_text(ref): decode verified bytes
-> verified_read_json(ref): parse verified bytes

Stage 04 artifact verification -> consume verified bytes, never verified-path-then-reread
Stage 06 progress evidence     -> consume verified bytes
new adversarial tests:
  tampered bytes rejected
  malformed ref rejected
  missing artifact rejected
  path escape rejected
  symlink substitution rejected
  deterministic swap-after-first-read / second-read regression rejected
full regression + Stage 03-07 probes
```

Only after this passes may the Stage-02 nested-submount reproduction and later Stage-08 runtime/state/context implementation proceed.
