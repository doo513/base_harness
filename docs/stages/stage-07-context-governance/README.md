# Stage 07 — Context Governance

Status: **PASS CANDIDATE — v0.8.0 RELEASE VERIFICATION PENDING**

## Purpose

Stage 07 introduces a deterministic Context Governor between durable harness state and the model-visible Actor prompt.

The objective is not semantic summarization quality. The objective is a projection boundary that is:

- trust-preserving;
- bounded for compressible/untrusted material;
- deterministic across resume;
- provenance-bound;
- evidence-retaining;
- resistant to untrusted instruction confusion;
- unable to silently remove mandatory goal/control requirements.

## Implemented

- namespaced `ContextPolicy` / `ContextProjector`;
- mandatory goal, acceptance, constraints, pinned constraints, current trusted facts and control state;
- trusted / speculative / observational separation;
- superseded facts excluded from current truth;
- deterministic duplicate collapse and bounded observation/tool previews;
- raw artifact-reference retention;
- model-visible untrusted `instruction_authority=none` boundary;
- context-policy provenance and fail-closed resume drift;
- deterministic same-state/same-policy projection;
- non-serialized trusted-controller compatibility for moved legacy fields;
- one governed Python/JSON value for real Stage-07 keys;
- Context Governor as the sole runtime `_context()` implementation;
- build/runtime package-version consistency regression.

## Candidate evidence

`v0.8.0rc5` candidate commit `757ec837c7a0eb83bdab71c497851fef196f13e8`, Actions `31943066462`:

```text
pytest                    125 passed / 5 skipped
Stage 03-06 probes         PASS
Stage 07 base              4 / 4 PASS
Stage 07 adversarial       6 / 6 PASS
Stage 07 resume            3 / 3 PASS
Stage 07 compatibility     3 / 3 PASS
Stage 07 zero counters     all 0
```

## Candidate-history note

The Stage was not promoted at the first green build. Re-review found insufficient legacy-value-schema testing, an invalid hidden-`tools` compatibility expectation, a dormant raw `_context()` implementation, and package-version source divergence. Each issue was closed and regression-tested before release eligibility.

## Explicit boundaries

- Mandatory goal/trusted/control data is not universally lossy; an arbitrarily large mandatory state can still produce a large prompt.
- `valid_until` is surfaced but not interpreted using wall-clock time in this deterministic Stage.
- Selection is deterministic, not semantic relevance ranking.
- Stage 07 does not implement RAG, embeddings, long-term memory, LLM summarization, skills, subagents, or planner hierarchy.
- Future retrieval/memory content must enter through this gateway as untrusted evidence unless separately verified.

See `CONTRACT.md`, `../../STAGE7_PREFLIGHT_REREVIEW.md`, `../../STAGE7_IMPLEMENTATION_REPORT.md`, `../../STAGE7_EVIDENCE_MATRIX.md`, `../../STAGE7_FINAL_REREVIEW.md`, and `../../STAGE7_EXIT_DECISION.md`.
