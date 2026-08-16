# Stage 08 Final Re-review

Release: `v0.9.0`  
Commit: `a5645fc9d059afd12088ee1c4751c0250c8a5206`  
CI: `31954492789` — SUCCESS

## Review question

Does the release implementation satisfy the frozen Stage08 Retrieval / Memory Gateway contract without creating a new bypass across State, Verification, Progress, Context, Persistence or earlier isolation guarantees?

## Code-structure review

### State boundary — PASS

Retrieval lives in a dedicated durable `RetrievalState`. It is not encoded as a verified fact or ordinary successful observation. Snapshot/load/resume owns the retrieval substate explicitly.

### Verification/integrity boundary — PASS

Candidate content is SHA-bound to provider/source identity, stored content-addressed, and consumed through the shared single-buffer verified-read primitive. Current model-visible items are re-verified before projection.

No path-return API is treated as verified content authority.

### Progress boundary — PASS

Retrieval actions do not create ordinary observations and receive no Stage06 progress credit. Base and previous Stage06 probes confirm retrieval-only activity does not reset no-progress.

### Context boundary — PASS

Retrieval is projected only in the untrusted namespace with fixed `instruction_authority=none`. Count/text/metadata bounds apply before model serialization. Stage07 compatibility remains green.

### Query/provider boundary — PASS within frozen scope

Actor controls explicit query text only. Kernel normalizes and owns/validates scope, top-k, provider/index identity, ranking contract, admission, request identity and result/history bounds.

Provider descriptor is frozen before search and compared with the post-search descriptor. The same inspected provider snapshot is used for candidate identity/admission. No semantic query-planner claim is made.

### Batch admission boundary — PASS

All candidates are prepared and verified before live retrieval state/ref mutation. An injected second-candidate integrity failure leaves live retrieval items, snapshots, artifact/evidence refs and retrieval metrics unchanged.

The state-side batch is therefore atomic with respect to HarnessState authority. This is intentionally narrower than claiming an atomic transaction over physical artifact-file creation, event log and checkpoint filesystem operations.

### Supersession boundary — PASS

Freshness is not inferred from ranking or lexical revision order. Supersession is an explicit Kernel transition. Superseded historical items do not silently re-enter the current set.

### Persistence/resume boundary — PASS

Runtime config fingerprints retrieval policy/provider/index configuration. Resume validates durable retrieval request identities, provider identity and referenced artifacts before model-visible reuse. Missing/tampered artifacts and provider/index drift fail closed.

### Failure routing — PASS

Retrieval storage `OSError` is converted into `PersistenceError`; the public dispatch path records a persistence failure rather than misclassifying storage failure as an implementation defect.

### Earlier Stage regression — PASS

Release CI passed Stage03 resume, Stage04 semantic verification, Stage05 recovery suites, Stage06 progress suites, Stage07 context suites and Stage02 remediation probes on the same commit.

## Defects discovered during implementation

1. Stage07 mixin extension compatibility regression — fixed.
2. Provider descriptor inspected/consumed object mismatch — fixed by frozen snapshot reuse.
3. Inconsistent bound-test fixtures — corrected without weakening production policy.
4. Per-candidate live-state mutation allowing partial batch admission — fixed with prepare-then-batch-commit.
5. Proposed query canonicalization that would alter persisted semantics — rejected/reverted before release.
6. Correctness `assert` removable under `python -O` — replaced with explicit `IntegrityError`.
7. Retrieval artifact-write `OSError` could map to implementation failure — fixed and tested.

## Release evidence

```text
verified-state-harness 0.9.0
182 passed, 5 skipped in 14.54s
Stage08 base        4/4 PASS
Stage08 adversarial 6/6 PASS
Stage08 resume      4/4 PASS
Stage08 cost        PASS
Artifact integrity  6/6 PASS
Earlier Stage/probe regression PASS
```

## Residual limitations

### R08-L1 — unreferenced artifact GC

Failed preparation can leave content-addressed files that were written before a later candidate failed. They are not in authoritative HarnessState/evidence refs and cannot become model-visible via normal state projection, but can consume disk space.

Severity for Stage08 truth guarantee: **LOW / operational**.  
Future work: content-addressed orphan inventory/GC with conservative retention.

### R08-L2 — semantic query planning

Actor supplies explicit query text. Stage08 constrains the admitted retrieval descriptor but does not semantically derive a query from goal/unknown/failure state.

Severity for frozen Stage08 contract: **NON-BLOCKING / explicit scope boundary**.

### R08-L3 — arbitrary remote provider honesty

The shipped local lexical provider is deterministic and inspected by tests. A future remote provider could lie about hidden internal mutation despite a stable descriptor unless a stronger provider-specific proof/interface is added.

Severity: **NON-BLOCKING for current shipped provider; HIGHER review requirement for future remote providers**.

### R08-L4 — filesystem-wide transaction scope

Batch atomicity is a HarnessState authority guarantee, not a universal transaction spanning every artifact file, event-log append and checkpoint write. Stage03 durability semantics continue to govern those files.

Severity: **NON-BLOCKING / claim-scope limitation**.

## Final blocker check

- Critical: **0**
- High: **0** for the frozen Stage08/current local-provider scope
- unresolved release-blocking contract violations: **0**

## Exit decision

**PASS / EXITED — Stage 08, `v0.9.0`.**

This decision is evidence-scoped. It does not close independent clean-host isolation, real-world verifier coverage, Recovery effectiveness, task/world progress semantics or oversized mandatory goal/control remediation items from earlier Stages.
