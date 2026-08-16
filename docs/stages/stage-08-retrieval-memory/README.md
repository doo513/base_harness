# Stage 08 — Retrieval / Memory Gateway

Status: **RELEASE SNAPSHOT — `v0.9.0`; exit pending same-commit CI**

Frozen contract: [`CONTRACT.md`](./CONTRACT.md)

## Objective

Stage 08 adds a durable, deterministic and bounded retrieval/evidence gateway without allowing retrieved material to become trusted truth, completion authority, recovery authority or progress by itself.

## Implemented architecture

```text
Actor explicit retrieval request
  -> Kernel request normalization + policy framing
  -> frozen provider/index descriptor
  -> deterministic read-only Gateway search
  -> candidate identity/content/source validation
  -> content-addressed artifact write + verified read
  -> prepare complete batch
  -> single live HarnessState-side RetrievalState/ref commit
  -> checkpoint/resume
  -> Context Governor
       trust = untrusted_retrieval
       instruction_authority = none
```

### Ownership boundary

Actor-controlled:

- explicit retrieval query text only.

Kernel-controlled or Kernel-validated:

- query normalization and durable request ID,
- scope,
- top-k,
- provider/index identity and revision,
- deterministic ranking policy,
- candidate/source/content admission,
- content/result/history budgets,
- supersession transition,
- durable request/result state,
- context projection authority and bounds.

This Stage does **not** claim a semantic Kernel query planner. That is intentionally separate from the current frozen scope.

## Core guarantees

1. **Evidence, not truth** — retrieval items cannot directly enter `facts` or complete the task.
2. **No instruction authority** — model-visible retrieval is always `untrusted_retrieval` / `instruction_authority=none`.
3. **No false progress** — retrieval is stored outside ordinary `Observation`; retrieval-only actions get Stage06 progress credit 0.
4. **Deterministic provider contract** — provider descriptor includes stable provider/index identity, index hash and ranking-policy version; mutation during search is rejected.
5. **Content integrity** — candidate digest, content-addressed artifact ref and verified bytes must agree.
6. **Batch state atomicity** — all candidate artifacts are prepared/verified before live `RetrievalState`, artifact refs, evidence refs and metrics are committed as one state-side batch.
7. **Bounded growth** — query/source/provider fields, content bytes, metadata, visible preview, durable items and request snapshots are bounded.
8. **Explicit supersession** — ranking order never silently decides freshness; Kernel supersession is a separate durable transition.
9. **Resume fail-closed** — state/artifact/provider/index/config drift is verified before restored retrieval becomes model-visible.
10. **Stage07 compatibility** — retrieval projection uses an extension hook; Stage07-only runtimes keep their previous context contract.

## Pre-release evidence

Implementation candidate:

`a9fab5d446ff574d2bd090f51226f7f366585d15`

Candidate CI run:

`31954088822`

Release candidate:

`8bd4454d8f6d6ed7ec4ab568a70c9aca67629e06` (`v0.9.0rc1`)

RC CI run:

`31954351977` — SUCCESS

Candidate results reproduced by RC:

- full pytest: **182 passed / 5 skipped**;
- Stage08 base: **4/4 PASS**;
- Stage08 adversarial: **6/6 PASS**;
- Stage08 resume: **4/4 PASS**;
- Stage08 cost: **PASS**;
- single-buffer artifact integrity: **6/6 PASS**;
- Stage03–07 regression probes: **PASS**;
- Stage02 remediation probes: **PASS**.

The final `v0.9.0` snapshot must reproduce this complete gate before Stage 08 is marked PASS / EXITED.

## Residual limitations

- Failed preparation may leave **unreferenced content-addressed files**. They are not referenced by HarnessState and have no truth/context authority, but later GC may be desirable for disk hygiene.
- The shipped local lexical gateway is the concrete deterministic provider proved by current tests. Stage08 does not prove that an arbitrary remote provider cannot lie about hidden internal mutation.
- Actor query text remains explicit input. Kernel owns the admitted retrieval descriptor, but semantic query planning is not implemented.
- Stage08 reuses the Stage03 state/event/checkpoint durability model; it does not add a universal cross-filesystem transaction abstraction.

## Exit artifacts

After final release CI passes, this directory is finalized with:

- `IMPLEMENTATION_REPORT.md`
- `EVIDENCE_MATRIX.md`
- `COST_REPORT.md`
- `FINAL_REREVIEW.md`

and machine-readable Stage08 evidence under `evidence/`.
