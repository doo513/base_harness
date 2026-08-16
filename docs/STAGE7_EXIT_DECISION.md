# Stage 07 — Exit Decision

Decision: **PASS / EXITED**  
Release: `v0.8.0`  
Release commit: `e53c7d8e16c4fdfc814150026c0a9fa64df026e6`  
Release GitHub Actions: `31943274153`

## Exit criteria

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

## Actual release verification

The actual `v0.8.0` release snapshot was independently executed after version promotion:

```text
installed package                 verified-state-harness 0.8.0
compileall                        PASS
pytest                            125 passed / 5 skipped
Stage 03 resume                   4 / 4 PASS; duplicate external actions 0
Stage 04 semantic                 8 / 8 PASS; FP=0/FN=0
Stage 05 all probes               PASS
Stage 06 all probes               PASS
Stage 07 base                     4 / 4 PASS
Stage 07 adversarial              6 / 6 PASS
Stage 07 resume                   3 / 3 PASS
Stage 07 compatibility            3 / 3 PASS
missing mandatory constraints     0
projection state mutations        0
raw evidence deletions            0
untrusted authority promotions    0
superseded current-truth exposure 0
policy drift acceptances          0
projection resume divergence      0
model-visible legacy raw values   0
legacy moved-schema breakages     0
Python/JSON split-brain keys      0
```

Five skipped tests are hosted-environment live Linux namespace tests and are not counted as Stage 02 production-isolation proof.

## What this PASS means

The built-in Actor/model path receives a deterministic, provenance-bound Context-Governor projection rather than broad raw HarnessState. Optional/untrusted material can be bounded and reorganized without rewriting epistemic authority, promoting speculative content, dropping mandatory goal/control state, or exposing superseded truth as current. Context-policy drift fails closed on resume.

Trusted in-process Controllers retain compatibility access to moved legacy fields through detached non-serialized snapshots, while model JSON never receives those raw compatibility values. Actual Stage-07 top-level keys have a single governed Python/JSON value.

## What this PASS does not mean

Stage 07 does not establish semantic relevance ranking, universal fixed total prompt size, wall-clock freshness evaluation, RAG, embeddings, long-term memory, automatic summarization, skills, subagents, model routing, or trusted retrieval. Retrieval/memory candidates remain untrusted unless the existing verification path promotes them.

## Next allowed Stage

**Stage 08 — Retrieval / Memory Gateway**.

Stage 08 must begin with a preflight re-review and a frozen Retrieval/Memory Admission Contract. It must define source identity, provenance, integrity, trust level, write authority, deterministic retrieval inputs, context-budget interaction, resume behavior, and the rule that retrieved or remembered material cannot directly mutate verified facts or completion state.
