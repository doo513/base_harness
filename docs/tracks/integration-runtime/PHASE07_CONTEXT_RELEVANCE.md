# Phase 07 — Active Context Relevance

Status: IMPLEMENTED; deterministic relevance tests added; Stage-07 base projection remains unchanged.

## Problem / evidence

Stage 07 correctly bounded and separated trusted/untrusted/control context, but selection was intentionally authority/key/recency driven rather than task-relevance driven. In real development this can surface strong but irrelevant facts while the Actor is working on a narrower active task.

## Contract

- trust determines authority; relevance determines visibility priority only;
- relevance is deterministic and Kernel-owned, not an LLM judgment;
- current goal/acceptance/constraints and persisted Agent Control objective/active task form the lexical focus query;
- relevant facts keep their existing verified authority;
- hypotheses/observations remain explicitly untrusted and instruction-authority-free;
- relevance cannot grant progress, completion, or verification authority;
- the original Stage-07 projection remains intact and the focus view is an additional bounded namespace.

## Implementation

- added `ActiveContextPolicy` and `ActiveContextProjector`;
- deterministic Unicode lexical tokenization and weighted overlap ranking;
- active task title/note receives higher relevance weight than broad goal text;
- stable tie-breaking preserves deterministic replay;
- bounded focused facts/hypotheses/observations with small previews and omission counts;
- Runtime context now exposes `active_context` alongside the original Stage-07 namespaces;
- `active_context` declares `truth_authority=none` and `progress_authority=false`.

## Structural review

- no `HarnessState` mutation occurs during relevance projection;
- no claim status/authority is recalculated from relevance;
- no base `ContextProjector` behavior or Stage-07 legacy compatibility path is removed;
- untrusted content containing instruction-like text remains `instruction_authority=none`;
- deterministic lexical ranking avoids introducing a second LLM/judge into the Kernel control path.

## Validation focus

`tests/test_integration_context_relevance.py` covers:

- active-task selection over a stronger but unrelated verified fact;
- preservation of original fact authority;
- non-promotion of relevant hypotheses/observations;
- deterministic repeated projection;
- bounded selection and previews.

## Remaining limitations

- lexical overlap is intentionally simple and does not claim semantic relevance;
- embeddings/vector ranking may later be plugged in only as an untrusted candidate-ranking aid, not truth authority;
- focused context is additive, so token-cost benefit must be measured during Real E2E before reducing the original Stage-07 projection.
