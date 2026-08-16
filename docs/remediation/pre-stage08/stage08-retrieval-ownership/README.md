# Stage08 remediation — Retrieval Query Ownership / Admission

Finding IDs: `R08-RETRIEVAL-002`, `R08-ATOMIC-001`, `R08-IO-001`  
Status: **CLOSED for Stage08 frozen scope — `v0.9.0`**

Release commit: `a5645fc9d059afd12088ee1c4751c0250c8a5206`  
Release CI: `31954492789` — SUCCESS

This directory is the remediation history. It records why the Stage08 implementation changed, not only the final design.

## Original problem

The old `src/harness/core/memory.py` prototype was unsuitable for Stage08 because it combined evidence retrieval with weak authority/state semantics:

- arbitrary authority string;
- same-ID silent overwrite;
- search-side `recall_count` mutation;
- no explicit deterministic tie-break;
- no provider/source/index provenance contract;
- no artifact-integrity binding;
- no durable resume contract;
- no explicit supersession transition;
- no typed context boundary preventing instruction authority.

The prototype was therefore not extended into the Stage08 runtime path.

## Evidence-based implementation path

### 1. Shared verified-read prerequisite

An early centralized artifact helper still had a verify-read / return-read TOCTOU class. Stage08 admission was blocked until the primitive became single-buffer:

```text
open one file object
-> read bytes once
-> hash exactly those bytes
-> return exactly those bytes
```

Release prerequisite probe: 6/6 PASS, unverified return buffers `0`.

### 2. Separate retrieval state from Observation/Facts

To preserve Stage06/Stage04 semantics, retrieval results were given a dedicated durable `RetrievalState`. They are not successful observations and do not become verified facts on admission.

Direct evidence: retrieval progress events `0`; direct fact/completion mutations `0`.

### 3. Explicit ownership split

Final Stage08 ownership is:

Actor:

- explicit query text.

Kernel-owned or Kernel-validated:

- whitespace normalization and durable request identity;
- allowed scope;
- top-k;
- provider/index identity and revision;
- index hash;
- deterministic ranking contract;
- candidate/source/content admission;
- content/result/history/context budgets;
- supersession transition;
- durable result snapshot;
- model-visible trust/authority.

Stage08 does not claim semantic Kernel query planning.

### 4. Provider same-object correction

Review found repeated `gateway.descriptor()` calls could make the descriptor inspected before search differ from the identity later consumed for candidate admission.

Correction:

- validate/freeze provider descriptor before search;
- obtain an after-search descriptor only to detect mutation;
- use the original frozen snapshot for request identity, candidate identity and admission.

### 5. Batch atomicity correction

Review found the first working candidate mutated live retrieval state once per admitted item. A later candidate failure could therefore leave an earlier candidate authoritative even though the request failed.

Correction:

```text
validate + bound complete result set
-> prepare/write/verify all candidates without live-state mutation
-> clone RetrievalState/artifact refs/evidence refs
-> apply complete batch to clones
-> require Kernel STATE_COMMIT
-> replace live state-side structures
```

Injected second-item integrity failure produced:

- live retrieval items `0`;
- live request snapshots `0`;
- live authoritative artifact refs `0`;
- unchanged retrieval metrics.

Physical content-addressed files may remain unreferenced; this is recorded as an operational GC residual, not hidden as a transaction guarantee.

### 6. Failure-classification correction

Final re-review found artifact-write `OSError` could fall through to generic implementation error handling.

Correction: wrap artifact-write I/O as `PersistenceError`; verify both direct and public decision-dispatch paths. Public failure kind is now `persistence_error` with target `retrieval`.

## Failed/intermediate validations retained

- first context integration broke Stage07 standalone mixin compatibility; fixed with a no-op extension hook;
- new bound tests initially used internally inconsistent policy fixtures (`max_context_items` larger than admission cap); fixtures were corrected without weakening policy;
- a proposed stronger query canonicalization was rejected because it would silently change persisted query semantics and break multiword resume compatibility;
- correctness `assert` was replaced by explicit `IntegrityError` because optimized Python may remove assertions.

## Release evidence

```text
verified-state-harness 0.9.0
182 passed, 5 skipped in 14.54s
Stage08 base        4/4 PASS
Stage08 adversarial 6/6 PASS
Stage08 resume      4/4 PASS
Stage08 cost        PASS
Artifact integrity  6/6 PASS
Prior Stage/P0 regression PASS
```

## Current disposition

### R08-RETRIEVAL-002 — CLOSED

The runtime now makes the Actor-controlled query field explicit and makes the remaining retrieval descriptor/admission fields Kernel-owned or Kernel-validated. Retrieval is always projected as untrusted data and gives no direct progress credit.

### R08-ATOMIC-001 — CLOSED for HarnessState authority

A failed batch cannot partially commit live retrieval state/refs/metrics. No broader cross-filesystem transaction claim is made.

### R08-IO-001 — CLOSED

Retrieval artifact write I/O maps to persistence failure and leaves retrieval authority state clean.

## Residuals

- unreferenced content-addressed artifact GC is not implemented;
- semantic query planning is not implemented;
- arbitrary remote-provider hidden-state honesty is not proved by the local-provider evidence;
- Stage03 durability continues to define event/checkpoint filesystem semantics.

Canonical Stage08 reports are under `docs/stages/stage-08-retrieval-memory/`. The remediation-specific reports in this directory preserve the defect/action lineage.
