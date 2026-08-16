# 03 — Next Stage Task

# Stage 06 — Loop / Progress Control

Version target: `v0.7.0` only after PASS.

## Entry condition

Stage 05 Failure Recovery must be PASS / EXITED with durable recovery scheduling/application, no known security/persistence retry bypass, and no unresolved Critical/High recovery defect. Entry is satisfied by `v0.6.0` once the release snapshot CI succeeds.

## Research question

How can the Kernel distinguish **meaningful progress** from repeated/no-progress behavior without trusting the Actor to self-report progress and without turning a heuristic similarity score into truth authority?

## First action

Freeze a **Progress Contract** before implementation.

It must define:

1. which observable state changes count as progress;
2. normalized action/failure/target/purpose signatures;
3. relationship to `strategy_generation`;
4. when progress resets a no-progress counter;
5. when repetition triggers Stage 05 `REPLAN`, `SWITCH_STRATEGY`, or terminal escalation;
6. budget accounting for repeated work;
7. persistence/resume behavior for progress state;
8. false-positive protection so equivalent useful retries are not blocked incorrectly;
9. false-negative protection so cosmetic argument changes do not evade loop detection;
10. evidence required before any semantic extension beyond deterministic signatures.

## Initial constraint

Do **not** begin with embeddings, an LLM judge, a planner hierarchy, or a general semantic similarity subsystem. Start with deterministic, inspectable progress signals and a synthetic adversarial matrix.

## Candidate observable signals

- verified fact set/hash change;
- new integrity-checked evidence/artifact;
- hypothesis/refutation state change;
- completion-oracle result change;
- tool target/purpose/action signature;
- repeated failure signature within a strategy generation;
- strategy generation change;
- explicit unknown resolved/introduced.

These are candidates, not yet frozen semantics.

## Required preservation

- Actor cannot self-promote progress into truth.
- Stage 03 receipt semantics remain authoritative for side effects.
- Stage 04 verification remains authoritative for facts.
- Stage 05 recovery remains kernel-owned.
- no hidden retry loop outside hard budget.

## Exit direction

PASS requires direct evidence that repeated non-progress paths are bounded and cause deterministic recovery/escalation while legitimate evidence-producing retries continue, with Stage 01–05 regression preserved.
