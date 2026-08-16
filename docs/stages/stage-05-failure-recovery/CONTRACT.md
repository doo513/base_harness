# Stage 05 Recovery Transition Contract

Status: **SATISFIED / EXITED by v0.6.0**

## Research question

Can failure recovery become a kernel-owned, durable, deterministic transition without bypassing truth authority, tool isolation, persistence receipts, semantic verification, or the completion oracle?

Answer for the declared Stage 05 scope: **yes, with the boundaries below**.

## Core invariant

> Recovery may change recovery-control state and targeted untrusted speculative state, but it may not manufacture verified facts, replay ambiguous external effects, bypass capability checks, or declare completion.

## Recovery ownership

- `FailureRouter` selects a recovery class from a typed failure.
- Kernel schedules one `RecoveryTransition` for that failure record.
- Kernel persists scheduling before returning from `fail()`.
- Kernel applies pending recovery before asking the Actor for another decision.
- Actor receives a bounded directive but cannot mark recovery applied or alter recovery history.
- Applied/terminal recovery state is persisted and survives resume.

## Recovery actions and allowed mutations

| Action | Allowed kernel mutation | Forbidden |
|---|---|---|
| `REPAIR` | issue repair directive | direct tool execution; fact mutation |
| `OBSERVE` | issue observation directive | evidence fabrication |
| `REPLAN` | issue replan directive | verifier/oracle bypass |
| `RETRY` | permit retry only when failure is explicitly retry-safe | automatic replay |
| `ROLLBACK` | remove targeted untrusted hypothesis/speculative state | verified fact/filesystem/receipt/external rollback |
| `SWITCH_STRATEGY` | increment durable strategy generation | changing truth authority |
| `ESCALATE` | persist terminal external-intervention requirement and halt | silent continuation |
| `CHECKPOINT_STOP` | persist terminal fail-closed halt | automatic continuation |

## Security and side effects

1. `SECURITY_VIOLATION` routes to terminal `CHECKPOINT_STOP`.
2. `PERSISTENCE_ERROR` routes to terminal `CHECKPOINT_STOP`.
3. PREPARED-only non-idempotent receipts are never automatically replayed.
4. Recovery never invokes a tool itself.
5. `RETRY` is permission only. Unsafe/unknown ENV retry degrades to `OBSERVE`.
6. Verified-fact hash must remain unchanged across a recovery transition.

## Failure identity and repeat escalation

- Default failure signature preserves semantically meaningful numbers and normalizes whitespace.
- A caller may provide `signature_key` when it knows how to remove volatile request IDs/paths safely.
- Repeat counting is scoped to the **current `strategy_generation`**.
- At the configured threshold, non-terminal recovery becomes `SWITCH_STRATEGY`.
- Applying `SWITCH_STRATEGY` increments generation.
- The same failure in the new generation begins again at repeat count 1 rather than immediately switching again.
- Terminal failure kinds never turn back into automatic recovery paths because of repeat count.

## Budget rule

Recovery is not an out-of-band free loop.

- When hard budget remains at the recovery application boundary, a recovery transition consumes one normal harness step and wall-clock time.
- If hard budget is already exhausted, the terminal fail-closed checkpoint transition is administrative and does **not** increment the persisted step beyond the hard limit.
- If budget expires after a non-terminal recovery was scheduled but before it is applied, that transition is superseded by `BUDGET_EXCEEDED -> CHECKPOINT_STOP` before the non-terminal mutation occurs.

## Persistence rule

The following are part of `HarnessState.snapshot()`:

- pending recovery transition;
- recovery history;
- active recovery directive;
- strategy generation;
- terminal recovery halt state.

### Scheduling commit point

```text
failure routed
-> pending RecoveryTransition created
-> failure record updated
-> state snapshot/checkpoint committed
-> descriptive failure/recovery.scheduled audit events
```

The snapshot is authoritative. A crash after the snapshot but before the descriptive audit event does not lose recovery state.

### Application commit point

```text
pending recovery applied
-> state/history/directive updated
-> state snapshot/checkpoint committed
-> descriptive recovery.transition audit event
```

Resume reconstructs the persisted state and applies any pending recovery before Actor execution. An already terminally halted recovery remains halted.

## Controller state dependency

Stateful controllers must implement both:

```text
snapshot_state() -> JSON object
restore_state(raw)
```

This prevents Actor decision cursors from restarting after a recovery/resume boundary. Controller runtime state is distinct from immutable controller configuration provenance.

## Rollback boundary

`ROLLBACK` means **logical rollback of targeted untrusted speculative state only**. Stage 05 makes no claim that arbitrary filesystem, remote-service, physical, or already committed external effects can be undone. External side effects remain governed by Stage 03 receipt semantics.

## Exit evidence

Final candidate `v0.6.0-rc6`, commit `c50a4bd15a86b3e26bf1fe52c15edde61738edd0`, GitHub Actions `31936441736`:

```text
pytest                             94 passed / 5 skipped
Stage 03 resume                    4 / 4 PASS; duplicate=0
Stage 04 semantic                  8 / 8 PASS; FP=0; FN=0
Stage 05 base recovery             PASS
Stage 05 adversarial               PASS
Stage 05 terminal                  PASS
Stage 05 crash window              PASS
Stage 05 strategy generation       PASS
unsafe retries                     0
verified fact mutations            0
ambiguous external executions      0
lost scheduled recoveries          0
hard-budget step overshoot          0
```

The 5 skips are hosted-environment live Linux namespace tests and are not Stage 02 production evidence.

## Non-goals / guarantee boundary

Stage 05 does not implement or claim:
- semantic loop/no-progress detection;
- guaranteed LLM compliance with a recovery directive;
- exactly-once Actor directive delivery;
- general external transaction rollback;
- planner hierarchy, RAG, skills, subagents, or model routing.
