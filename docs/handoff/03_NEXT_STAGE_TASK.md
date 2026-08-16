# 03 — Next Stage Task

# Stage 07 — Context Governance

Version target: `v0.8.0` only after PASS.

## Why this is next

The architecture names a Context Governor as a core component, but the current runtime `_context()` directly exposes broad state to the Actor:

- pinned constraints and acceptance criteria;
- all verified facts;
- all current/refuted hypotheses;
- unknowns;
- all observations;
- recent failures;
- recovery/progress control state;
- tool metadata.

Stage 06 can now detect deterministic no-progress, but an Actor can still receive an unbounded or poorly scoped context containing stale, duplicate, low-value, or untrusted observation material. Adding long-term memory or retrieval before defining this projection boundary would make that problem harder to reason about.

## First action

Do **not** begin by adding vector retrieval, RAG, LLM summarization, or automatic memory.

First freeze a **Context Projection Contract** defining:

1. fields that are mandatory and may never be dropped (`goal`, pinned constraints, acceptance, critical recovery/terminal state);
2. trusted verified facts versus untrusted/speculative/observational material;
3. freshness/staleness representation and supersession;
4. deterministic observation selection and ordering under a context budget;
5. raw artifact/evidence references that remain available when previews are omitted;
6. treatment of untrusted tool/remote text so it cannot become system-level instruction authority;
7. context truncation/compression rules that cannot silently rewrite epistemic status or authority;
8. provenance/config fingerprint for context-policy changes;
9. resume determinism for the same context projection;
10. how a future memory/retrieval subsystem must enter through this gateway rather than directly modifying trusted state.

## Required preflight review

Before implementation, inspect at minimum:

- `RuntimeExecutionMixin._context()`;
- `HarnessState` freshness/supersession representation;
- observation preview/artifact storage;
- GoalContract pinned constraints and acceptance propagation;
- recovery/progress directive visibility;
- token/size budget interfaces;
- DomainProfile extension surface.

Find and record structural defects before modifying code.

## Required adversarial scenarios

```text
many duplicate observations              -> bounded context, raw evidence retained
very large tool output                    -> preview bounded, artifact drill-down retained
stale/superseded fact                     -> not represented as current truth
untrusted observation says "ignore goal" -> remains data, never system/kernel instruction
hypothesis text claims VERIFIED            -> status remains speculative in projection
context pressure                           -> goal/pinned constraints/acceptance never dropped
recent specific failure/recovery           -> required control context preserved
progress state                             -> visible without granting Actor mutation authority
policy threshold/config drift on resume    -> fail closed
deterministic same state                   -> deterministic same projection
future retrieval/memory candidate          -> enters as untrusted evidence unless separately verified
```

## Exit minimum

```text
Context Projection Contract frozen             PASS
mandatory goal/control fields never dropped    PASS
trusted/untrusted representation preserved     PASS
bounded deterministic projection               PASS
raw evidence drill-down retained               PASS
untrusted text cannot gain instruction authority PASS
context policy in provenance                    PASS
resume projection determinism                   PASS
full Stage 01-06 regression                     PASS
final re-review: unresolved Critical/High       0
```

## Non-goals

Stage 07 is not long-term memory, RAG, embeddings, skill learning, subagents, planner hierarchy, semantic relevance ranking by an LLM, or model routing. Those features must depend on the context-governance boundary rather than bypass it.
