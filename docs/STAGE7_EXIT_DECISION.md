# Stage 07 — Exit Decision

Decision: **PASS candidate — release snapshot verification required**  
Target release: `v0.8.0`  
Final candidate: `757ec837c7a0eb83bdab71c497851fef196f13e8`

## Candidate exit criteria

```text
Context Projection Contract frozen          PASS
single runtime context projection boundary  PASS
mandatory goal/control retained             PASS
trusted/untrusted separation                PASS
bounded deterministic optional projection   PASS
raw evidence references retained            PASS
untrusted instruction authority             NONE
superseded current-truth exposure            0
context policy provenance                    PASS
resume projection determinism                PASS
legacy moved-schema compatibility            PASS
model-visible legacy raw values              0
Python/JSON split-brain context keys         0
build/runtime version consistency            PASS
full regression                              PASS
prior Stage probes                           PASS
unresolved Critical/High                     0
```

## Candidate verification

GitHub Actions run `31943066462`:

```text
installed package                 0.8.0rc5
pytest                            125 passed / 5 skipped
Stage 03 resume                   4 / 4 PASS; duplicate=0
Stage 04 semantic                 8 / 8 PASS; FP=0/FN=0
Stage 05 probes                   PASS
Stage 06 probes                   PASS
Stage 07 base                     4 / 4 PASS
Stage 07 adversarial              6 / 6 PASS
Stage 07 resume                   3 / 3 PASS
Stage 07 compatibility            3 / 3 PASS
zero-tolerance Stage 07 counters  all 0
```

## Meaning of PASS

On successful `v0.8.0` release-snapshot verification, Stage 07 establishes that the built-in Actor/model path receives a deterministic Context-Governor projection rather than broad raw HarnessState. Projection cannot promote speculative material to trusted truth, drop mandatory goal/control state, silently change on resume under policy drift, or leak trusted-controller compatibility snapshots into model JSON.

## Scope boundaries

This decision does not claim semantic relevance ranking, universal fixed prompt size, wall-clock freshness interpretation, RAG, embeddings, long-term memory, or trusted retrieval. Any future retrieval/memory material must remain evidence/untrusted input until existing verification promotes it.

## Next allowed research direction

After `v0.8.0` is actually verified and this document is updated to **PASS / EXITED**, the next research candidate is **Stage 08 — Retrieval / Memory Gateway**. Stage 08 must begin with a contract and preflight review; implementation must not start by adding a vector database or automatic memory writes.
