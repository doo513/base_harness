# Stage 07 — Context Governance

Status: **PASS / EXITED**  
Release: `v0.8.0`  
Release commit: `e53c7d8e16c4fdfc814150026c0a9fa64df026e6`  
Release Actions: `31943274153`

## Purpose

Stage 07 introduces a deterministic Context Governor between durable harness state and the model-visible Actor prompt.

The objective is a projection boundary that is trust-preserving, deterministic across resume, provenance-bound, evidence-retaining, bounded for optional/untrusted material, and unable to silently remove mandatory goal/control requirements.

## Implemented

- namespaced `ContextPolicy` / `ContextProjector`;
- mandatory goal, acceptance, ordinary constraints, pinned constraints, current trusted facts and critical control state;
- trusted / speculative / observational separation;
- superseded facts excluded from current truth;
- deterministic duplicate collapse and bounded observation/tool previews;
- raw artifact-reference retention;
- untrusted `instruction_authority=none` model boundary;
- context-policy provenance and fail-closed resume drift;
- deterministic same-state/same-policy projection;
- non-serialized trusted-controller compatibility for moved legacy fields;
- one governed Python/JSON value for real Stage-07 keys;
- Context Governor as the sole runtime `_context()` implementation;
- build/runtime package-version consistency regression.

## Release evidence

```text
installed package            0.8.0
pytest                       125 passed / 5 skipped
Stage 03-06 probes            PASS
Stage 07 base                 4 / 4 PASS
Stage 07 adversarial          6 / 6 PASS
Stage 07 resume               3 / 3 PASS
Stage 07 compatibility        3 / 3 PASS
Stage 07 zero counters        all 0
```

## Discovered defects before exit

Stage 07 was not promoted at the first green build. Re-review found and closed:

1. legacy key aliases that did not preserve old raw value schema;
2. an invalid compatibility expectation that could have made `tools` return different Python and JSON values;
3. a dormant pre-Stage-07 raw `_context()` implementation in `RuntimeExecutionMixin`;
4. divergent package-version sources between `harness.__version__` and `pyproject.toml`.

Each issue is regression-tested.

## Explicit boundaries

- Mandatory goal/trusted/control data is not universally lossy; arbitrarily large mandatory state can still produce a large prompt.
- `valid_until` is surfaced but not interpreted using wall-clock time in this deterministic Stage.
- Selection is deterministic, not semantic relevance ranking.
- Stage 07 does not implement RAG, embeddings, long-term memory, LLM summarization, skills, subagents, or planner hierarchy.
- Future retrieval/memory content must enter through this gateway as untrusted evidence unless separately verified.

See `CONTRACT.md`, `../../STAGE7_PREFLIGHT_REREVIEW.md`, `../../STAGE7_IMPLEMENTATION_REPORT.md`, `../../STAGE7_EVIDENCE_MATRIX.md`, `../../STAGE7_FINAL_REREVIEW.md`, and `../../STAGE7_EXIT_DECISION.md`.
