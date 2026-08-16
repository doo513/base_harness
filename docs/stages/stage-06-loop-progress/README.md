# Stage 06 — Loop / Progress Control

Status: **IN PROGRESS — CONTRACT FROZEN**.

Target release: `v0.7.0` only after all gates PASS.

## Purpose

Stage 06 adds deterministic, kernel-owned progress accounting on top of Stage 05 recovery. It is intended to bound repeated successful-but-unproductive Actor behavior that does not naturally enter the typed failure path.

## Design order

```text
preflight re-review
-> freeze Progress Contract
-> implement durable ProgressState + policy descriptor
-> evaluate Actor decision outcome only
-> schedule NO_PROGRESS through Stage 05
-> add strategy-exhaustion terminal path
-> adversarial matrix
-> resume/provenance tests
-> full Stage 01–05 regression
-> final logic/implementation/structure re-review
-> PASS/PARTIAL/FAIL
```

## Important distinction

Stage 05 already handles explicit failures such as tool errors, verification failures, security violations, and persistence ambiguity. Stage 06 must not replace those routes.

Stage 06 focuses on paths such as:

- repeated successful tool calls that return the same evidence;
- repeated speculative state churn;
- alternating Actor decisions that consume budget but add no verified state or novel successful evidence;
- repeated completion requests rejected without any intervening progress.

## Authority boundary

Progress is a control signal only. It does not grant semantic truth authority and cannot directly create verified facts or accept completion.

See `CONTRACT.md` for the frozen semantics and adversarial exit matrix.
