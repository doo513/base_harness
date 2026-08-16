# Stage 08 — Retrieval / Memory Gateway

Status: **PASS / EXITED — `v0.9.0`**

Frozen contract: [`CONTRACT.md`](./CONTRACT.md)

Release commit: `a5645fc9d059afd12088ee1c4751c0250c8a5206`  
Release CI: `31954492789` — **SUCCESS**

## Objective

Stage 08 adds a durable, deterministic and bounded retrieval/evidence gateway without allowing retrieved material to become trusted truth, completion authority, recovery authority or progress by itself.

## Architecture

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

Stage 08 does **not** claim a semantic Kernel query planner.

## Exit guarantees

1. Retrieval is evidence, never trusted truth by admission alone.
2. Model-visible retrieval is always `untrusted_retrieval` / `instruction_authority=none`.
3. Retrieval is stored outside ordinary `Observation`, so retrieval itself gives Stage06 progress credit 0.
4. Provider/index descriptor, ranking-policy version and read-only declaration are validated; descriptor mutation during search fails closed.
5. Candidate digest, content-addressed artifact ref and verified bytes must agree.
6. A candidate-batch failure does not partially mutate live `RetrievalState`, artifact/evidence refs or retrieval metrics.
7. Query/source/provider fields, result/content bytes, metadata, context preview, durable items and request history are bounded.
8. Supersession is an explicit Kernel transition rather than an inference from ranking order.
9. Resume fails closed on missing/tampered retrieval artifacts and provider/index/config drift.
10. Stage07-only context implementations remain compatible through an explicit retrieval projection extension hook.

## Release evidence

- package: `verified-state-harness 0.9.0`;
- full pytest: **182 passed / 5 skipped in 14.54s**;
- Stage08 base: **4/4 PASS**;
- Stage08 adversarial: **6/6 PASS**;
- Stage08 resume: **4/4 PASS**;
- Stage08 cost: **PASS**;
- single-buffer artifact integrity: **6/6 PASS**, unverified return buffers `0`;
- Stage03–07 direct regression probes: **PASS**;
- Stage02 remediation probes: **PASS**.

Environment recorded by the release CI:

- Ubuntu 24.04.4 / GitHub runner image `ubuntu-24.04`, version `20260810.271.1`;
- CPython `3.11.15`;
- Git `2.54.0`;
- pytest `9.1.1` from the locked CI requirements.

## Reports

- [`IMPLEMENTATION_REPORT.md`](./IMPLEMENTATION_REPORT.md)
- [`EVIDENCE_MATRIX.md`](./EVIDENCE_MATRIX.md)
- [`COST_REPORT.md`](./COST_REPORT.md)
- [`FINAL_REREVIEW.md`](./FINAL_REREVIEW.md)

## Residual limitations

- Failed preparation may leave **unreferenced content-addressed files**. They are not referenced by HarnessState and have no truth/context authority, but later GC may be desirable for disk hygiene.
- The shipped local lexical gateway is the concrete deterministic provider proved by current tests. Stage08 does not prove that an arbitrary remote provider cannot lie about hidden internal mutation.
- Actor query text remains explicit input. Kernel owns the admitted retrieval descriptor, but semantic query planning is not implemented.
- Stage08 reuses the Stage03 event/state/checkpoint durability model; it does not add a universal cross-filesystem transaction abstraction.
