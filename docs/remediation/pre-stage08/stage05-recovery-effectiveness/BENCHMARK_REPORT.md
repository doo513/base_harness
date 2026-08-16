# Stage05 Recovery Effectiveness — Benchmark Report

## Purpose

Measure whether the already-shipped Stage05 recovery-control mechanism changes task outcome under matched deterministic failure injection. Production recovery code was not modified to obtain the result.

## Experimental design

### A — Recovery

Production `FailureRouter` and normal durable `RecoveryTransition` path.

### B — No automatic recovery

A benchmark-only router preserves terminal safety behavior but maps the first nonterminal failure to `CHECKPOINT_STOP`.

For every pair, goal, controller implementation/state, tools, initial environment, budget, failure point and completion oracle are identical. Only failure routing differs.

## Scenarios

### tool_repair

- injected primary tool error;
- baseline: halted after first failure;
- Recovery: `repair` directive, Actor selects alternate tool, independent oracle accepts.
- result: Recovery completed; baseline did not.

### missing_info_observe

- initial claim path produces `missing_info`;
- baseline: halted;
- Recovery: `observe` directive, Actor gathers deterministic information, then alternate path succeeds.
- result: Recovery completed; baseline did not.

### verification_replan

- first completion attempt is rejected by the same completion oracle;
- baseline: halted;
- Recovery: `replan` directive, Actor takes alternate path and later passes the oracle.
- result: Recovery completed; baseline did not.

### terminal_security

- generic WRITE handler under strict isolation;
- both arms halt on `security_violation`;
- unsafe handler calls: `0` in both arms.

This verifies the benchmark does not count unsafe continuation as effectiveness.

## Aggregate result

```text
recoverable scenarios                 3
Recovery completion                   3/3 = 1.0
No-recovery completion                0/3 = 0.0
completion-rate delta                 +1.0
recovered pairs                       3
additional steps total                7
additional tool calls total           4
additional steps / recovered success  2.3333333333333335
additional tools / recovered success  1.3333333333333333
terminal safety regressions           0
control-integrity violations          0
```

All tool execution following a recovery transition remained Actor-mediated; recovery itself executed no task tool and created no verified fact. Unsafe retries were zero.

## Validation environment

GitHub Actions run `31955531150`:

- commit `1b8496c120f52496d53de90ef7aae013cc926962`;
- package `verified-state-harness 0.9.0`;
- pytest `182 passed, 5 skipped in 14.59s`;
- previous Stage03–08 and Stage02 remediation probes all PASS.

## Interpretation boundary

The benchmark is intentionally constructed to isolate recovery routing as the causal variable. That makes the A/B attribution strong **inside this benchmark**, but external validity is weak: it is not a natural model/task corpus and has only three recoverable scenario families.

Disposition: **controlled benchmark PASS; broad real-world effectiveness still OPEN.**
