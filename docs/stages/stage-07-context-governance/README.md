# Stage 07 — Context Governance

Status: **IN PROGRESS — CONTRACT FROZEN**

Target release: `v0.8.0` only after all gates PASS.

## Purpose

Stage 07 introduces a deterministic Context Governor between durable harness state and the model-visible Actor prompt.

The goal is not summarization quality. The goal is to make context selection:

- trust-preserving;
- bounded for compressible/untrusted material;
- deterministic across resume;
- provenance-bound;
- evidence-retaining;
- resistant to untrusted tool-text instruction confusion;
- unable to remove mandatory goal/control requirements.

## Design order

```text
v0.7.0 baseline re-review
-> freeze Context Projection Contract
-> implement ContextPolicy + pure projection
-> harden built-in LLMController trust instructions
-> targeted unit/integration tests
-> direct projection probe
-> adversarial trust/injection probe
-> determinism/resume probe
-> full Stage 03-06 regression
-> final logic/implementation/structure re-review
-> evidence + implementation/error/methodology + exit docs
-> PASS/PARTIAL/FAIL
```

## Explicit non-goals

Do not add RAG, embeddings, long-term memory, LLM summarization, semantic relevance ranking, planner hierarchy, or subagents in this Stage.

See `CONTRACT.md` and `../../STAGE7_PREFLIGHT_REREVIEW.md`.
