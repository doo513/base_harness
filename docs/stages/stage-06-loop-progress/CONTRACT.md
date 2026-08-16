# Stage 06 Progress Contract

Status: **FROZEN BEFORE IMPLEMENTATION; RC3 CLARIFICATION RECORDED**

Target release: `v0.7.0` only after PASS.

## Research question

Can the Kernel bound deterministic repeated/no-progress behavior without trusting Actor self-reporting, without treating heuristic similarity as truth authority, and without weakening Stage 01–05 guarantees?

## Core invariant

> Progress is a kernel-derived control signal, not a truth claim. Actor text, reasons, hypotheses, and cosmetic decision-payload changes cannot self-declare progress.

Stage 06 is allowed to decide whether execution should continue, replan, switch strategy, or escalate. It is **not** allowed to promote a fact, accept completion, bypass verification, replay an ambiguous side effect, or weaken the hard budget.

## Progress authority

The Kernel owns progress accounting. The Actor cannot set any progress counter or mark an action as productive.

Progress has two deterministic evidence classes:

1. **verified-state progress** — the canonical hash of verified semantic fact content changes through the existing Stage 04 commit path. The progress fingerprint covers fact key/value/status/authority but intentionally excludes evidence-reference metadata so ref churn cannot manufacture progress;
2. **novel successful observation progress** — a successful tool observation references a content-addressed JSON artifact whose raw bytes still match the SHA-256 encoded in the artifact reference and whose canonical decoded JSON content fingerprint has not previously appeared in successful observations.

Canonical JSON comparison ignores mapping-key insertion order. **String values are preserved exactly** because whitespace can be semantically meaningful in source code, configuration, signatures, and other domain data.

The following do **not** independently count as progress:

- Actor narrative or `complete.reason` text;
- new/reworded hypothesis text;
- refuting or re-proposing speculative state;
- failure/recovery bookkeeping;
- strategy-generation increment by itself;
- creation of another artifact reference whose canonical successful-observation content is already known;
- failed tool output, even when the error text changes;
- evidence-reference metadata churn on an otherwise unchanged verified fact;
- cosmetic JSON mapping-key order changes.

Novel observation progress is intentionally a syntactic evidence-novelty signal, not a claim that the evidence is semantically useful. Semantic relevance remains outside Stage 06.

### RC3 clarification

The pre-implementation contract said string whitespace was normalized for **decision identity**. An rc2 implementation review found that applying the same normalization to verified facts or evidence content could erase meaningful source-code indentation or formatting. The contract is therefore clarified, not broadened:

- Actor decision identity collapses cosmetic string whitespace;
- verified fact values and successful evidence string values preserve exact content.

This distinction prevents loop-evasion through reworded Actor payloads without creating false no-progress classifications for whitespace-sensitive verified data.

## Decision signatures

Every Actor decision produces two deterministic signatures.

### Family signature

Used for coarse repetition detection and intentionally resistant to cosmetic payload variation.

```text
propose      -> propose:<claim-key>
verify_claim -> verify_claim:<claim-key>
refute       -> refute:<claim-key>
tool         -> tool:<tool-name>
complete     -> complete
```

### Exact signature

Used for audit/debugging. It hashes a recursively normalized **Actor decision payload**:

- mapping keys sorted canonically;
- whitespace collapsed in Actor-supplied strings;
- numbers preserved;
- list order preserved;
- `complete.reason` is excluded from repetition identity because it is Actor-controlled narrative;
- refute reason is excluded from repetition identity for the same reason.

Changing JSON key order, adding cosmetic whitespace, or rephrasing a completion/refutation reason therefore cannot manufacture a new decision identity.

The family signature is the primary anti-evasion signal; the exact signature is not sufficient by itself to establish progress.

## Durable progress state

`HarnessState.snapshot()` must include progress-control state sufficient for deterministic resume:

- progress strategy generation;
- consecutive no-progress Actor decision count;
- last no-progress family signature;
- consecutive same-family no-progress count;
- total Actor progress evaluations;
- total recognized progress events;
- last progress step;
- last progress strategy generation;
- last progress reason(s);
- count of no-progress threshold triggers.

The existing observations/facts remain the source of truth for fact hashes and successful evidence fingerprints; Stage 06 does not maintain a second mutable evidence database.

## Strategy-generation semantics

When `state.strategy_generation` changes:

- same-family and local no-progress counters reset;
- strategy switch itself is **not** progress;
- prior successful evidence remains known, so rediscovering identical canonical content in a new strategy is not novel progress;
- last actual progress generation is preserved for strategy-exhaustion accounting.

## No-progress triggers

Two deterministic triggers exist.

1. **same-family window** — the same decision family produces no recognized progress for `family_repeat_limit` Actor decisions;
2. **global no-progress window** — consecutive Actor decisions produce no recognized progress for `no_progress_streak_limit`, even if the Actor alternates families.

A recognized progress event resets both windows.

A trigger schedules `FailureKind.NO_PROGRESS` through the existing Stage 05 `fail()` path. It does not execute recovery directly.

The global trigger uses a stable failure action/signature independent of the latest decision family, so alternating families still participate in one Stage 05 repeat/escalation identity.

After scheduling one no-progress failure, the local trigger window resets. This prevents a single threshold crossing from generating a new failure on every subsequent Actor step.

## Existing failure precedence

If the Actor decision already scheduled a more specific pending recovery (tool error, verification failure, persistence error, security violation, etc.), Stage 06 must **not** schedule an additional `NO_PROGRESS` failure for that decision.

Specific Stage 05 failure semantics take precedence.

## Recovery-step rule

Recovery transitions are not Actor decisions and are not evaluated as progress/no-progress actions. They still consume the existing harness step budget exactly as defined in Stage 05.

## Strategy exhaustion

A strategy switch is a control transition, not progress. If execution reaches `max_strategy_generations_without_progress` generations beyond the last recognized progress generation and the current Actor decision still makes no progress, the Kernel schedules `FailureKind.STRATEGY_EXHAUSTED`.

Stage 05 then routes it to terminal `ESCALATE`.

Any recognized progress updates the last-progress generation and resets this exhaustion horizon.

## Budget rule

Stage 06 creates no hidden retry loop and no separate budget. Actor decisions, Stage 05 recovery transitions, and terminalization remain governed by the existing hard step/wall budget.

## Persistence / crash rule

Progress state is committed by the existing outer actor-step checkpoint so the Actor decision, controller cursor, state mutation, progress counters, and normal step increment remain one replay unit.

If Stage 06 schedules a failure, Stage 05 `fail()` remains the authoritative immediate recovery-scheduling commit point.

Stage 06 must not introduce an earlier standalone progress checkpoint that advances the controller cursor without the normal actor-step transition.

Before each new Actor decision, all historical successful-observation artifacts used as progress evidence are integrity checked. A missing or modified artifact schedules terminal `PERSISTENCE_ERROR` before the next Actor decision is consumed.

## Provenance rule

The complete progress policy/threshold descriptor is included in the run manifest configuration fingerprint. Resume with a different policy must fail closed under the existing Stage 03/04 reproducibility checks.

## Required adversarial matrix

```text
verified fact semantic change            -> progress
verified fact evidence-ref churn         -> no progress
new successful artifact content          -> progress
duplicate successful artifact content    -> no progress
failed tool with changing errors          -> no progress
reworded complete reason                  -> same family / no evasion
Actor JSON key-order/whitespace change    -> same normalized decision identity
evidence JSON key-order change            -> same content fingerprint
whitespace-sensitive evidence/fact value  -> distinct content when value differs
repeated speculative proposals            -> no self-promoted progress
alternating unproductive families         -> global no-progress trigger
same unproductive family                  -> family trigger
specific tool failure + no progress       -> specific failure preserved, no NO_PROGRESS supersession
recovery transition                       -> not counted as Actor no-progress
strategy switch                           -> local counters reset, not progress
same evidence after strategy switch       -> still not novel
progress after strategy switch            -> exhaustion horizon reset
multi-generation no progress              -> STRATEGY_EXHAUSTED -> ESCALATE
pending progress state + resume            -> deterministic continuation
progress policy drift on resume            -> fail closed
new artifact content tamper                -> never progress
historical successful artifact tamper      -> terminal before next Actor
```

## Exit criteria

```text
Stage 06 unit/integration tests                 PASS
Stage 06 deterministic matrix                   PASS
Stage 06 adversarial/evasion probe              PASS
Stage 06 boundary probe                         PASS
Stage 06 strategy/exhaustion probe              PASS
Stage 06 resume/durability probe                PASS
full regression                                 PASS
Stage 03 resume probe                           PASS
Stage 04 semantic probe                         PASS
Stage 05 recovery probes                        PASS
Actor self-reported progress acceptance         0
cosmetic decision loop-evasion cases            0
specific-failure supersessions by NO_PROGRESS   0
recovery steps counted as Actor no-progress     0
artifact-tamper progress acceptance             0
historical-tamper Actor continuation             0
unresolved Critical/High finding                0
```

## Non-goals / guarantee boundary

Stage 06 does not implement embeddings, an LLM progress judge, semantic relevance scoring, planner hierarchy, RAG, subagents, model routing, or universal novelty detection.

In particular, a tool that legitimately emits different canonical content on every call (for example a changing timestamp, nonce, random sample, or continuously changing environment) may continue to register syntactic observation novelty even when a human would judge the strategy semantically unproductive. Hard budget still bounds execution, but semantic usefulness of novel evidence is not claimed by Stage 06.
