# Stage 06 Progress Contract

Status: **FROZEN BEFORE IMPLEMENTATION**

Target release: `v0.7.0` only after PASS.

## Research question

Can the Kernel bound deterministic repeated/no-progress behavior without trusting Actor self-reporting, without treating heuristic similarity as truth authority, and without weakening Stage 01–05 guarantees?

## Core invariant

> Progress is a kernel-derived control signal, not a truth claim. Actor text, reasons, hypotheses, and cosmetic payload changes cannot self-declare progress.

Stage 06 is allowed to decide whether execution should continue, replan, switch strategy, or escalate. It is **not** allowed to promote a fact, accept completion, bypass verification, replay an ambiguous side effect, or weaken the hard budget.

## Progress authority

The Kernel owns progress accounting. The Actor cannot set any progress counter or mark an action as productive.

Progress has two deterministic evidence classes:

1. **verified-state progress** — the content hash of the verified fact set changes through the existing Stage 04 commit path;
2. **novel successful observation progress** — a successful tool observation adds a content-addressed artifact whose bytes still match the digest encoded in its artifact reference and whose content digest has not previously appeared in successful observations.

The following do **not** independently count as progress:

- Actor narrative or `complete.reason` text;
- new/reworded hypothesis text;
- refuting or re-proposing speculative state;
- failure/recovery bookkeeping;
- strategy-generation increment by itself;
- creation of another artifact reference whose content digest is already known;
- failed tool output, even when the error text changes;
- changes that exist only in cosmetic JSON key order or string whitespace.

Novel observation progress is intentionally a syntactic evidence-novelty signal, not a claim that the evidence is semantically useful. Semantic relevance remains outside Stage 06.

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

Used for audit/debugging. It hashes a recursively normalized payload:

- mapping keys sorted canonically;
- whitespace collapsed in strings;
- numbers preserved;
- list order preserved;
- `complete.reason` is excluded from repetition identity because it is Actor-controlled narrative;
- refute reason is excluded from repetition identity for the same reason.

Changing JSON key order, adding whitespace, or rephrasing a completion/refutation reason therefore cannot manufacture a new progress identity.

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

The existing observations/facts remain the source of truth for fact hashes and successful evidence digests; Stage 06 does not maintain a second mutable evidence database.

## Strategy-generation semantics

When `state.strategy_generation` changes:

- same-family and local no-progress counters reset;
- strategy switch itself is **not** progress;
- prior successful evidence remains known, so rediscovering identical bytes in a new strategy is not novel progress;
- last actual progress generation is preserved for strategy-exhaustion accounting.

## No-progress triggers

Two deterministic triggers exist.

1. **same-family window** — the same decision family produces no recognized progress for `family_repeat_limit` Actor decisions;
2. **global no-progress window** — consecutive Actor decisions produce no recognized progress for `no_progress_streak_limit`, even if the Actor alternates families.

A recognized progress event resets both windows.

A trigger schedules `FailureKind.NO_PROGRESS` through the existing Stage 05 `fail()` path. It does not execute recovery directly.

The failure uses a stable explicit `signature_key` based on the trigger class/family so cosmetic payload changes cannot evade Stage 05 repeat accounting.

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

## Provenance rule

The complete progress policy/threshold descriptor is included in the run manifest configuration fingerprint. Resume with a different policy must fail closed under the existing Stage 03/04 reproducibility checks.

## Required adversarial matrix

```text
verified fact change                  -> progress
new successful artifact bytes         -> progress
duplicate successful artifact bytes   -> no progress
failed tool with changing errors       -> no progress
reworded complete reason               -> same family / no evasion
JSON key-order/whitespace change       -> same normalized exact identity
repeated speculative proposals         -> no self-promoted progress
alternating unproductive families      -> global no-progress trigger
same unproductive family               -> family trigger
specific tool failure + no progress    -> specific failure preserved, no NO_PROGRESS supersession
recovery transition                    -> not counted as Actor no-progress
strategy switch                        -> local counters reset, not progress
same evidence after strategy switch    -> still not novel
progress after strategy switch         -> exhaustion horizon reset
multi-generation no progress           -> STRATEGY_EXHAUSTED -> ESCALATE
pending progress state + resume         -> deterministic continuation
progress policy drift on resume         -> fail closed
artifact content tamper                 -> terminal persistence/integrity failure, never progress
```

## Exit criteria

```text
Stage 06 unit/integration tests                 PASS
Stage 06 deterministic matrix                   PASS
Stage 06 adversarial/evasion probe              PASS
Stage 06 resume/durability probe                PASS
full regression                                 PASS
Stage 03 resume probe                           PASS
Stage 04 semantic probe                         PASS
Stage 05 recovery probes                        PASS
Actor self-reported progress acceptance         0
cosmetic loop-evasion cases                     0
specific-failure supersessions by NO_PROGRESS   0
recovery steps counted as Actor no-progress     0
artifact-tamper progress acceptance             0
unresolved Critical/High finding                0
```

## Non-goals

Stage 06 does not implement embeddings, an LLM progress judge, semantic relevance scoring, planner hierarchy, RAG, subagents, model routing, universal novelty detection, or proof that novel evidence is useful to the task.
