# 03 — Next Stage Task

# Stage 04 — Semantic Verification

Version target: `v0.5.0` only after PASS.

## Entry condition

Stage 03 Persistence / Resume / Reproducibility must be PASS with direct forced-kill, duplicate-effect, corruption, replay-hash, and provenance evidence.

Entry condition is satisfied by `v0.4.0`.

## First action

Do **not** immediately add new verifier breadth.

First re-review and freeze:

1. what a verifier is allowed to treat as evidence,
2. how evidence is bound to the exact claim being verified,
3. semantic false-positive / false-negative threat cases,
4. minimum independence required for each verification level,
5. when execution-level evidence is stronger than schema/logical evidence,
6. how Domain Profiles may customize verification without forking Kernel truth authority.

## Working objective

Move from “a verifier ran and returned true” toward **claim-bound semantic evidence whose relevance, authority, and independence are explicit and adversarially tested**.

## Required preservation rules

- Actor cannot promote trusted facts.
- Verifier cannot mutate Actor workspace unless explicitly using a separately authorized subprocess boundary.
- Oracle remains separate from Actor truth claims.
- resume/event/checkpoint/receipt invariants remain intact.
- no RAG, skill system, subagent swarm, planner hierarchy, or unrelated feature breadth.

## Exit rule

Stage 04 exit criteria must be written before implementation begins. If the semantic verifier still has known false-positive paths that can promote an incorrect claim, Stage 04 is PARTIAL/FAIL and Stage 05 must not begin.
