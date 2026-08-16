# Stage 08 Implementation Report — Retrieval / Memory Gateway

## Purpose

Stage 08 introduces retrieval as a bounded evidence source while preserving the harness invariant that retrieved text cannot become trusted truth, completion authority, recovery authority or progress merely because it was found.

Release: `v0.9.0`  
Release commit: `a5645fc9d059afd12088ee1c4751c0250c8a5206`  
Release CI: `31954492789`

## Entry findings

Stage08 preflight rejected the older `memory.py` prototype as an authority-bearing implementation base. The prototype allowed arbitrary authority strings, silent overwrite semantics, query-side recall mutation, weak deterministic ordering and no artifact/resume/supersession contract.

A second prerequisite defect was found in the shared artifact-integrity path: an early centralized verified-read candidate verified one read and could later return bytes from another read. That TOCTOU class was fixed before retrieval admission was allowed to depend on the primitive. The current primitive reads once, hashes that exact buffer and returns that exact buffer.

Stage06 and Stage07 boundaries were also treated as prerequisites:

- retrieval must not become a successful `Observation` that could reset no-progress;
- retrieval must reach the Actor only through the governed untrusted context namespace.

## Implemented components

### Typed retrieval model

`src/harness/core/retrieval.py` defines bounded typed state and policy for:

- `RetrievalPolicy`;
- `RetrievalRequest`;
- `RetrievalCandidate`;
- `RetrievalItem`;
- `RetrievalResultSnapshot`;
- `RetrievalState`;
- `RetrievalSourceItem`;
- deterministic local lexical gateway.

Stable identity binds provider ID/revision, source ID/revision/locator and content SHA-256.

### Durable state

`HarnessState` owns `RetrievalState` as a separate durable substate. It is serialized into checkpoint snapshots and restored on resume. Retrieval is therefore not encoded as ordinary observations or facts.

### Query/provider ownership

Actor controls only explicit query text. Kernel code normalizes it and owns or validates:

- scope;
- top-k;
- provider/index identity;
- index hash;
- deterministic ranking-policy version;
- candidate admission;
- durable request ID;
- result/content/history bounds.

The provider descriptor is frozen into deterministic JSON. Candidate validation and admission consume the same frozen descriptor snapshot rather than re-reading provider identity after inspection.

### Search purity and ranking

The shipped lexical provider declares `deterministic_replay=true` and `search_mutates_state=false`. Runtime validates these fields and rejects descriptor mutation observed across the search call. Equal-score results use an explicit deterministic total ordering.

### Artifact-backed admission

Every new retrieval item is written as content-addressed text, then verified through the single-buffer artifact read primitive. Candidate content hash, artifact-reference digest and returned bytes must agree.

Existing items are re-read and re-verified before repeated admission. Current model-visible items are re-verified before context projection.

### Batch state atomicity

Final re-review found a structural problem in the first integration: candidates were admitted one at a time, so candidate N failing could leave candidates 1..N-1 in live HarnessState.

The final design separates preparation from authoritative commit:

```text
validate result set
-> preflight capacities
-> prepare/write/verify every candidate without live-state mutation
-> clone RetrievalState + artifact/evidence reference lists
-> apply complete batch to clones
-> require Kernel STATE_COMMIT
-> replace live retrieval/ref state as one state-side batch
```

Injected second-candidate integrity failure leaves live retrieval items, request snapshots, artifact refs, evidence refs and retrieval metrics unchanged.

Physical content-addressed files created during preparation may remain unreferenced if a later preparation step fails; those files are explicitly non-authoritative and are listed as a residual GC concern.

### Supersession

An early design considered inferring supersession from retrieval order/revision. This was rejected because ranking is not freshness authority. Supersession is now an explicit Kernel-owned transition and superseded items are omitted from the current result set by default.

### Context boundary

Model-visible retrieval is projected only as:

```text
trust = untrusted_retrieval
instruction_authority = none
```

Projection is bounded by item count, preview characters and metadata budgets. Retrieval cannot directly mutate facts, completion or recovery state.

### Progress boundary

Retrieval is not inserted as a normal `Observation`. The Stage06 evaluator therefore receives no new evidence/fact transition merely from retrieval. Direct probes verify progress events remain zero for retrieval-only activity.

### Persistence and failure routing

Resume validates retrieval state, provider/index identity and all referenced artifacts before model-visible reuse.

Final re-review also found that raw `OSError` from retrieval artifact writes could be misclassified as an implementation failure. The write path now wraps storage I/O as `PersistenceError`; the public decision-dispatch path records `persistence_error` for the retrieval target.

## Important implementation failures and corrections

### 1. Stage07 mixin compatibility regression

Initial retrieval context integration assumed a retrieval mixin method always existed. Stage07 compatibility tests use `RuntimeContextMixin` independently, so this broke the older abstraction.

Correction: `RuntimeContextMixin` gained a no-op retrieval projection extension hook; the full runtime MRO overrides it only when retrieval is present.

### 2. Provider same-object violation

Initial code re-called `gateway.descriptor()` during validation/admission after search. That meant the descriptor inspected at the boundary was not necessarily the descriptor consumed during admission.

Correction: freeze one validated provider snapshot before search, compare with an after-search snapshot only for mutation detection, then consume the original frozen snapshot throughout request/candidate/admission processing.

### 3. Bound-test fixture failures

New tests reduced `max_admitted_per_request` to 1 or 2 while leaving `max_context_items=5`, correctly causing policy construction to reject the inconsistent fixture. The production policy was not weakened; fixtures were corrected.

### 4. Partial batch admission

Code review, not a green-test failure, identified that per-candidate live-state mutation could create partial authoritative results.

Correction: prepare the complete batch first and commit only cloned next-state structures.

### 5. Query semantic overreach avoided

A stronger case-fold/deduplicate/sort query transform was briefly considered. Review showed it would silently change persisted query semantics and conflict with the existing request-load invariant for multiword queries.

Correction: retain explicit Actor query semantics with deterministic whitespace normalization. Semantic Kernel query planning is documented as outside Stage08 scope.

### 6. Optimized-away assertion

A correctness invariant used Python `assert`, which disappears with `python -O`.

Correction: replace it with explicit `IntegrityError` fail-closed logic.

### 7. Storage-I/O failure mapping

Artifact write `OSError` could fall through to a generic implementation-error path.

Correction: wrap it as `PersistenceError` and add direct + public-dispatch tests.

## Release validation

Release CI `31954492789` on commit `a5645fc9d059afd12088ee1c4751c0250c8a5206`:

- package installed: `verified-state-harness 0.9.0`;
- pytest: `182 passed, 5 skipped in 14.54s`;
- Stage08 base: 4/4 PASS;
- Stage08 adversarial: 6/6 PASS;
- Stage08 resume: 4/4 PASS;
- Stage08 cost probe: PASS;
- artifact-integrity prerequisite: 6/6 PASS;
- all Stage03–07 regression probes: PASS;
- Stage02 nested-submount/backend-binding remediation probes: PASS.

## Exit decision

**PASS / EXITED — `v0.9.0`.**

The exit claim is limited to the frozen Stage08 contract and the concrete provider/runtime boundaries described above. Residual operational/research limitations are preserved in `FINAL_REREVIEW.md` rather than converted into hidden success claims.
