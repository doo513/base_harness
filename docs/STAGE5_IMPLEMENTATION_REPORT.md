# Stage 05 — Failure Recovery Implementation Report

Status: **PASS candidate for v0.6.0**  
Branch: `research/verified-state-stage03`  
Final candidate: `c50a4bd15a86b3e26bf1fe52c15edde61738edd0` (`v0.6.0-rc6`)

## 1. Objective

Stage 05 converts failure recovery from advisory text into a **kernel-owned, durable state transition** while preserving all earlier truth, capability, isolation, persistence, semantic verification, and completion-oracle gates.

The implemented flow is:

```text
Typed Failure
  -> FailureRouter
  -> RecoveryTransition(PENDING)
  -> immediate failure/recovery state checkpoint
  -> Kernel applies transition before Actor
  -> RecoveryTransition(APPLIED | SUPERSEDED)
  -> immediate transition checkpoint
  -> bounded recovery directive to Actor OR terminal halt
```

Recovery never directly executes an Actor tool and never writes a verified fact.

## 2. Preflight defects found before Stage 05

Stage 05 depended on deterministic resume, so existing persistence/provenance was re-reviewed first. Two preflight releases were created before recovery semantics were added.

### v0.5.1 — execution-semantic provenance

Closed:
- missing capability-policy fingerprint;
- ScriptedController script drift;
- completion-oracle command drift;
- predicate closure drift;
- tool handler/precondition/postcondition closure drift;
- execution/oracle backend configuration drift;
- incomplete source hashing across mixins/MRO.

Validation: GitHub Actions `31935087009`, 75 passed / 5 skipped, Stage 03 and Stage 04 direct probes PASS.

### v0.5.2 — stateful controller resume

Found that controller configuration was fingerprinted but `ScriptedController.index` was not checkpointed. Recovery transitions consume harness steps without consuming Actor decisions, so the cursor cannot be inferred from `HarnessState.step`.

Implemented an explicit controller checkpoint protocol:

```text
snapshot_state() -> JSON object
restore_state(raw)
```

Controller runtime state is stored in checkpoint runtime metadata and restored before Actor execution.

Validation: GitHub Actions `31935462946`, 76 passed / 5 skipped, controller cursor resume PASS, Stage 03/04 probes PASS.

## 3. Stage 05 implementation

### 3.1 Typed durable recovery state

Added:
- `RecoveryStatus`: `PENDING`, `APPLIED`, `SUPERSEDED`;
- `RecoveryTransition` with transition ID, typed action/failure, repeat count, strategy generation, target, retry safety, step metadata, and details;
- durable state fields: `pending_recovery`, `recovery_history`, `recovery_directive`, `strategy_generation`, `recovery_halted`, `recovery_halt_reason`.

These fields are included in `HarnessState.snapshot()` and are therefore covered by Stage 03 hash-chain/checkpoint/replay semantics.

### 3.2 Recovery authority

`FailureRouter` chooses the recovery class. The Kernel schedules and applies it. Actor code cannot mark a recovery transition APPLIED and cannot alter recovery history through a normal Decision.

Routing includes:
- TOOL_ERROR -> REPAIR
- MISSING_INFO -> OBSERVE
- VERIFICATION_FAILED -> REPLAN
- HYPOTHESIS_REFUTED -> ROLLBACK
- explicit retry-safe ENV_ERROR -> RETRY
- repeated failure at threshold -> SWITCH_STRATEGY
- SECURITY_VIOLATION / PERSISTENCE_ERROR / BUDGET_EXCEEDED -> CHECKPOINT_STOP
- STRATEGY_EXHAUSTED -> ESCALATE

Unsafe/unknown ENV retry is downgraded to OBSERVE.

### 3.3 Recovery is control-only

`RuntimeRecoveryMixin` applies control-state transitions. It does not invoke a tool.

`ROLLBACK` removes only the targeted untrusted hypothesis. It does not mutate verified facts, receipts, filesystem state, remote services, or arbitrary external state.

A hash of all verified facts is taken before/after each recovery transition; a mismatch is an integrity error.

### 3.4 Durable scheduling commit point

A critical crash window was found during rc5 review: scheduling recovery in memory and waiting for the ordinary outer-loop snapshot meant a process death could leave recovery events without durable `pending_recovery` state.

The corrected `fail()` sequence is:

```text
route failure
-> create RecoveryTransition
-> append failure state
-> _persist_state("failure.recovery.scheduled")   # authoritative commit point
-> descriptive failure/recovery.scheduled events
```

Therefore a crash immediately after `fail()` returns cannot lose the pending recovery or the post-Decision controller cursor.

### 3.5 Application ordering

`step_once()` checks pending recovery before calling the Actor. On resume, a persisted pending transition is therefore applied before the next Actor Decision.

Applied recovery is itself snapshotted before the descriptive `recovery.transition` audit event. The state snapshot/checkpoint is authoritative; the descriptive event may be absent if the process dies in the narrow post-snapshot audit window, but recovery state remains correct.

### 3.6 Security and persistence terminal handling

Security policy violations are a distinct `SECURITY_VIOLATION` failure kind and route to terminal `CHECKPOINT_STOP`.

PREPARED-only non-idempotent receipts remain ambiguous and are never replayed automatically. Stage 05 fixed an intermediate design where the runtime set `halted=True` before applying the recovery transition; terminality is now owned by the durable `CHECKPOINT_STOP` transition itself.

### 3.7 Budget handling

Normal recovery consumes a normal harness step while hard budget remains.

If hard budget is already exhausted, terminal checkpointing does not increment the persisted step beyond `hard_max_steps`.

If budget expires between scheduling and the actual recovery-application boundary, the non-terminal transition is durably superseded by `BUDGET_EXCEEDED -> CHECKPOINT_STOP` before it can mutate recovery state.

### 3.8 Repeat identity and strategy generation

An early implementation normalized every number in failure messages. That could make meaningful failures such as HTTP 401 and HTTP 500 share a signature. The default signature now preserves numbers and normalizes whitespace only. Callers may supply an explicit stable `signature_key` when known volatile values should be excluded.

A second review found that repeat count was global across the whole run. After one strategy switch, every later same-signature failure could therefore immediately switch strategy again. Repeat counting is now scoped to the **current `strategy_generation`**. After a strategy switch, the same failure starts again at repeat count 1 in the new generation.

## 4. Candidate history and errors discovered

| Candidate | Result | Finding |
|---|---|---|
| rc1 | FAIL | Old test assumed `step_once() -> None`; Stage 05 introduced explicit `False=Actor`, `True=recovery` contract. 85 passed / 5 skipped / 1 failed. |
| rc2 | PASS | Base durable recovery worked, but review found numeric signature collision, budget overshoot, and failure/audit linkage defects. |
| rc3 | PASS | Those defects closed; review then found incomplete durable terminal state for persistence ambiguity. |
| rc4 | PASS | Durable CHECKPOINT_STOP fixed; review then found recovery-scheduling crash window and recovery-boundary budget race. |
| rc5 | PASS | Crash window and boundary race closed; review then found repeat count not scoped by strategy generation. |
| rc6 | PASS | Repeat scope fixed; no unresolved Critical/High Stage 05 defect found in final review. |

## 5. Methodology

Stage 05 used failure-driven development rather than treating a green unit suite as sufficient:

1. Freeze Recovery Transition Contract.
2. Review prerequisites and repair resume/provenance first.
3. Implement one recovery meaning axis.
4. Add unit/integration tests.
5. Add direct runtime probes.
6. Run complete regression plus Stage 03/04 probes.
7. Re-read transition boundaries as crash points.
8. Add adversarial cases for every newly discovered defect.
9. Repeat until final review has no unresolved Critical/High item in scope.

No earlier gate was weakened to pass a later test.

## 6. Final candidate evidence

GitHub Actions run `31936441736`:

```text
compileall                         PASS
pytest                             94 passed / 5 skipped
Stage 03 resume probe              4 / 4 PASS
duplicate external actions        0
Stage 04 semantic matrix           8 / 8 PASS
Stage 04 false positives           0
Stage 04 false negatives           0
Stage 05 base recovery probe       PASS
Stage 05 adversarial probe         PASS
Stage 05 terminal probe            PASS
Stage 05 crash-window probe        PASS
Stage 05 strategy-generation probe PASS
unsafe automatic retries           0
verified fact mutations            0
ambiguous external executions      0
lost scheduled recoveries          0
hard-budget step overshoot          0
consecutive strategy switch bug     0
```

Five skips are production Linux namespace tests whose live `runtime_probe` is unavailable on this hosted runner. They are not counted as Stage 02 production proof and do not replace the previously recorded Stage 02 direct attack evidence.

## 7. Guarantee boundary

Stage 05 guarantees **durable kernel-owned recovery-control transitions**, not universal automatic repair.

It does not claim:
- that an LLM Actor will obey a REPAIR/REPLAN directive correctly;
- general semantic loop detection;
- exactly-once delivery of a recovery directive to Actor code across every crash point;
- transactional rollback of arbitrary external state;
- exactly-once effects in external systems;
- recovery from a physically unavailable/corrupt persistence medium.

External side effects remain governed by Stage 03 receipt semantics.
