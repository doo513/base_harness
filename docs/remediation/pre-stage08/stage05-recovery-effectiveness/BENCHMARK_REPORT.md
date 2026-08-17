# Stage05 Recovery Effectiveness — Benchmark Report

## Purpose

Measure whether the already-shipped Stage05 recovery-control mechanism changes task outcome under matched deterministic failure injection. Production recovery code was not modified to obtain the result.

## Experimental design

### A — Recovery

Production `FailureRouter` and normal durable `RecoveryTransition` path.

### B — No automatic recovery

A benchmark-only router preserves terminal safety behavior but maps the first nonterminal failure to `CHECKPOINT_STOP`.

For every pair, goal, controller implementation/state, tools, initial environment, budget, failure point, and completion oracle are identical. Only failure routing differs.

The benchmark is deterministic and is executed by:

```bash
python scripts/stage5_recovery_effectiveness_benchmark.py
```

The same command is also a required step in `.github/workflows/research-ci.yml`.

## Scenarios

### tool_repair

- injected primary tool error;
- baseline: halted after first failure;
- Recovery: `repair` directive, Actor selects alternate tool, completion oracle accepts;
- result: Recovery completed; baseline did not.

### missing_info_observe

- initial claim path produces `missing_info`;
- baseline: halted;
- Recovery: `observe` directive, Actor gathers deterministic information, then alternate path succeeds;
- result: Recovery completed; baseline did not.

### verification_replan

- first completion attempt is rejected by the same completion oracle;
- baseline: halted;
- Recovery: `replan` directive, Actor takes alternate path and later passes the oracle;
- result: Recovery completed; baseline did not.

### terminal_security

- generic WRITE handler under strict isolation;
- both arms halt on `security_violation`;
- unsafe handler calls: `0` in both arms.

This verifies that the benchmark does not count unsafe continuation as effectiveness. The terminal-security scenario is a safety control and is not included in the three-scenario completion-rate denominator.

## Re-run result — 2026-08-17

The benchmark was re-run against implementation commit `d5c375c9bf9e98b35dee1dfb6d1002e2a8126168` through the repository's `research-ci` workflow.

| Scenario | Recovery | No recovery | Recovery action | Step delta | Tool-call delta |
| --- | --- | --- | --- | ---: | ---: |
| `tool_repair` | completed, 4 steps, 2 tool calls | halted, 2 steps, 1 tool call | `repair` | +2 | +1 |
| `missing_info_observe` | completed, 5 steps, 2 tool calls | halted, 2 steps, 0 tool calls | `observe` | +3 | +2 |
| `verification_replan` | completed, 4 steps, 1 tool call | halted, 2 steps, 0 tool calls | `replan` | +2 | +1 |
| `terminal_security` | halted, unsafe handler calls 0 | halted, unsafe handler calls 0 | `checkpoint_stop` | 0 | 0 |

For every arm in the re-run:

- `tool_calls_actor_guarded = true`;
- `unsafe_retries = 0`;
- `verified_fact_count = 0`.

The terminal-security control passed in both arms, and the unsafe WRITE handler was never executed.

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
benchmark all_passed                   true
```

All tool execution following a recovery transition remained Actor-mediated; recovery itself executed no task tool and created no verified fact. Unsafe retries were zero.

## Validation environment

Fresh GitHub Actions re-run of run `31960200271`, verify job `95294825687`, on 2026-08-17:

- benchmarked commit `d5c375c9bf9e98b35dee1dfb6d1002e2a8126168`;
- Ubuntu `24.04.4` runner;
- CPython `3.11.15`;
- package `verified-state-harness 0.9.1`;
- pytest `209 passed, 5 skipped in 16.39s`;
- Stage05 recovery effectiveness A/B benchmark: `all_passed = true`;
- all Stage03–08 and Stage02 remediation probes executed by `research-ci` PASS.

This report update is documentation-only. The measured implementation commit above is the commit immediately preceding this report refresh; changing the report does not change the benchmarked runtime or benchmark script.

## Interpretation boundary

The benchmark is intentionally constructed to isolate recovery routing as the causal variable. That makes the A/B attribution strong **inside this benchmark**, but external validity remains weak: it is not a natural model/task corpus and has only three recoverable scenario families.

The observed `+1.0` completion-rate delta therefore demonstrates that the shipped recovery-control path changes outcomes for the three constructed failure families under matched deterministic conditions. It must not be interpreted as a `100%` recovery rate for arbitrary real-world tasks.

Disposition: **controlled benchmark PASS; current implementation re-validated; broad real-world effectiveness still OPEN.**
