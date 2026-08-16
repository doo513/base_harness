# Stage 05 Recovery Transition Contract

Status: **FROZEN BEFORE IMPLEMENTATION**

Target release: `v0.6.0` only after PASS.

## Research question

Can failure recovery become a kernel-owned, durable, deterministic transition without bypassing truth authority, tool isolation, persistence receipts, semantic verification, or the completion oracle?

## Core invariant

> Recovery may change recovery-control state and untrusted speculative state, but it may not manufacture verified facts, replay ambiguous external effects, bypass capability checks, or declare completion.

## Recovery ownership

- `FailureRouter` selects a recovery class from a typed failure.
- Kernel schedules exactly one `RecoveryTransition` for that failure record.
- Kernel applies pending recovery before asking the Actor for another decision.
- Actor receives a bounded recovery directive but cannot mark recovery applied or alter recovery history.
- Terminal recovery state is persisted and survives resume.

## Recovery actions and allowed mutations

| Action | Allowed kernel mutation | Forbidden |
|---|---|---|
| `REPAIR` | issue one repair directive | direct tool execution; fact mutation |
| `OBSERVE` | issue one observe directive | direct evidence fabrication |
| `REPLAN` | issue one replan directive | verifier/oracle bypass |
| `RETRY` | issue retry permission only when failure is explicitly retry-safe | automatic replay of the failed action |
| `ROLLBACK` | remove only targeted untrusted hypothesis/speculative state; issue rollback directive | reverting verified facts, filesystem, receipts, or arbitrary external state |
| `SWITCH_STRATEGY` | increment strategy generation and issue directive | changing truth authority |
| `ESCALATE` | persist terminal external-intervention requirement and halt | silent continuation |
| `CHECKPOINT_STOP` | persist terminal fail-closed halt | automatic retry/resume continuation |

## Security and side effects

1. Security violations are a distinct failure kind and must route to terminal `CHECKPOINT_STOP`.
2. Persistence ambiguity remains fail closed.
3. A PREPARED-only non-idempotent receipt is never automatically replayed by recovery.
4. Recovery never invokes a tool itself in Stage 05.
5. `RETRY` is a control directive, not execution. Unsafe/unknown retry requests are downgraded away from retry.

## Repeat/escalation rule

- Failure identity is based on normalized typed failure signature.
- At the configured repeat threshold, non-terminal recovery switches to `SWITCH_STRATEGY`.
- Terminal failures (`SECURITY_VIOLATION`, `PERSISTENCE_ERROR`, `BUDGET_EXCEEDED`) never switch back into an automatic recovery path.
- Strategy switching increments a durable generation counter so resume cannot repeat the same transition invisibly.

## Budget rule

A recovery transition consumes a normal harness step and wall-clock budget. There is no hidden recovery loop outside the existing hard budget. Recovery count is also recorded in metrics.

## Persistence rule

The following are part of `HarnessState.snapshot()` and therefore hash-chained/checkpointed:

- pending recovery transition
- recovery history
- active recovery directive
- strategy generation
- terminal recovery halt state

Resume must reconstruct these exactly. If a pending recovery exists, it is applied before the Actor is called. If terminal recovery halt is already persisted, resume remains halted.

## Rollback boundary

`ROLLBACK` means **logical rollback of untrusted speculative state only**. Stage 05 makes no claim that arbitrary filesystem, remote-service, or physical side effects can be undone. External side effects remain governed by Stage 03 receipt semantics.

## Required adversarial scenarios

```text
tool error                 -> durable REPAIR transition
missing information        -> durable OBSERVE transition
verification failure       -> durable REPLAN transition
refuted hypothesis         -> logical ROLLBACK only
same failure at threshold  -> one SWITCH_STRATEGY transition
security violation         -> CHECKPOINT_STOP, no retry
PREPARED-only receipt      -> no duplicate external action
pending recovery + resume  -> same transition applied before Actor
terminal recovery + resume -> remains halted
recovery transition        -> does not mutate verified facts
recovery transition        -> consumes normal step budget
```

## Exit criteria

```text
preflight provenance hardening       PASS
Stage 05 unit/integration tests       PASS
Stage 05 direct recovery probe       PASS
full regression                      PASS
Stage 03 direct resume probe         PASS
Stage 04 semantic probe              PASS
security retry bypass                0
ambiguous side-effect duplicates     0
verified-fact recovery mutation      0
resume recovery divergence           0
final logic/implementation/structure re-review: no unresolved Critical/High finding in Stage 05 scope
```

Stage 05 does not implement semantic loop detection, planner hierarchy, subagents, RAG, or general transactional rollback of the external world.
