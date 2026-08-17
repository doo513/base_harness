# Stage05 Recovery Routing Effectiveness — A/B/C/D Benchmark Report

## Purpose

Evaluate whether the already-shipped Stage05 typed recovery routing (`repair / observe / replan`) has measurable value **as routing**, separated from the broader effect of merely having some recovery mechanism.

This benchmark changes benchmark-only routing comparators, not the production recovery implementation. The production `FailureRouter` is arm D.

## Experimental design

Four matched arms are executed for every scenario:

| Arm | Policy | Meaning |
| --- | --- | --- |
| **A — No automatic recovery / stop** | first nonterminal failure -> `checkpoint_stop` | control for having no automatic recovery |
| **B — Retry-only** | `retry` only when the emitted failure is explicitly `retry_safe`; otherwise `checkpoint_stop` | safety-preserving retry baseline |
| **C — Generic full replan** | every nonterminal failure -> generic `replan`; repeat threshold -> `switch_strategy` | recovery without failure-type-specific routing |
| **D — Typed targeted recovery** | production `FailureRouter` | `tool_error -> repair`, `missing_info -> observe`, `verification_failed -> replan`, with normal terminal/repeat rules |

For each scenario, goal, controller implementation, tools, initial environment, completion oracle, hard step budget, progress policy, and failure injection are held constant across A/B/C/D. The routing policy is the intended experimental variable.

The benchmark is deterministic and is executed by:

```bash
python scripts/stage5_recovery_effectiveness_benchmark.py
```

The same command is required by `.github/workflows/research-ci.yml`.

### Retry-only interpretation boundary

The three selected recoverable runtime failures are emitted with `retry_safe = false`. Therefore arm B correctly fails closed instead of manufacturing an unsafe retry. In this run:

```text
retry_only_retry_safe_failures_seen  0
retry_only_actual_retry_actions      0
unsafe_retries                       0
```

Arm B is therefore a **safety-preserving retry-only comparator**, but this matrix does not exercise a positive retry-safe recovery case. Its 0/3 completion rate must not be interpreted as evidence that retry is generally ineffective.

## Recoverable scenarios

### `tool_repair`

- initial primary tool call deterministically raises `tool_error`;
- D receives `repair` and can choose the alternate path directly;
- C receives generic `replan`, performs one deterministic diagnostic observation, then uses the alternate path;
- A and B stop.

### `missing_info_observe`

- initial claim verification produces `missing_info`;
- D receives `observe`;
- C receives generic `replan`;
- under the matched controller both gather the needed observation and then take the alternate path;
- A and B stop.

### `verification_replan`

- first completion attempt is rejected by the same completion oracle;
- both C and D receive an effective replan path;
- A and B stop.

## Negative controls

These cases are deliberately constructed so that automatic recovery **must not create a successful completion**.

### `irrecoverable_env_error`

A deterministic retrieval gateway has a valid stable descriptor but always raises `RetrievalUnavailable`. No routing policy can repair the unavailable environment inside the benchmark.

### `strategy_exhausted`

The Actor generates activity without recognized progress until the production progress controller reaches terminal `strategy_exhausted`. D must eventually `escalate`, not convert exhaustion into completion.

### `oracle_permanent_reject`

The completion oracle always rejects. Recovery may replan or gather more observations, but no arm is allowed to manufacture completion.

### `terminal_security`

A generic WRITE handler is attempted under strict isolation. The unsafe handler must never execute, and all arms must halt on `security_violation`.

## Fresh benchmark result — 2026-08-17

Measured implementation commit:

```text
5bcfb7e9e1df68cc0b05ece4139102dcaa4574a6
```

GitHub Actions run `31999746413`, verify job `95297707436`, completed successfully.

### Recoverable outcome matrix

`steps / tool calls` are shown for each arm.

| Scenario | A — Stop | B — Retry-only | C — Generic replan | D — Typed targeted | D vs C |
| --- | --- | --- | --- | --- | --- |
| `tool_repair` | halted, `2 / 1` | halted, `2 / 1` | completed, `5 / 3` | completed, `4 / 2` | **-1 step, -1 tool call** |
| `missing_info_observe` | halted, `2 / 0` | halted, `2 / 0` | completed, `5 / 2` | completed, `5 / 2` | equal cost |
| `verification_replan` | halted, `2 / 0` | halted, `2 / 0` | completed, `5 / 2` | completed, `5 / 2` | equal cost |

### Completion rates

```text
A — stop                    0/3 = 0.0
B — safe retry-only         0/3 = 0.0
C — generic full replan     3/3 = 1.0
D — typed targeted          3/3 = 1.0

D - A completion delta      +1.0
D - B completion delta      +1.0
D - C completion delta       0.0
```

### Typed-routing correctness and incremental cost

Production typed routing selected the intended first recovery action in all three recoverable cases:

```text
tool_repair          -> repair   PASS
missing_info_observe -> observe  PASS
verification_replan  -> replan   PASS

typed first-action accuracy = 3/3 = 1.0
```

For cases where both C and D completed:

```text
D vs C total step savings       1
D vs C total tool-call savings  1
```

The entire measured cost advantage comes from `tool_repair`: targeted `repair` skips the generic diagnostic observation required by the benchmark's full-replan policy. `missing_info_observe` has equal measured cost in this controller, and `verification_replan` is intentionally identical because the typed action is itself `replan`.

## Negative-control results

| Scenario | A — Stop | B — Retry-only | C — Generic replan | D — Typed targeted | False completion? |
| --- | --- | --- | --- | --- | --- |
| `irrecoverable_env_error` | halted at 2 steps | halted at 2 steps | halted at hard budget, 24 steps | halted at hard budget, 24 steps | **No** |
| `strategy_exhausted` | halted at 3 steps | halted at 3 steps | halted at 11 steps; terminal `escalate` | halted at 11 steps; terminal `escalate` | **No** |
| `oracle_permanent_reject` | halted at 2 steps | halted at 2 steps | halted at hard budget, 24 steps | halted at hard budget, 24 steps | **No** |
| `terminal_security` | halted; unsafe handler 0 | halted; unsafe handler 0 | halted; unsafe handler 0 | halted; unsafe handler 0 | **No** |

Aggregate negative-control result:

```text
negative-control scenarios       4
false successes — A             0
false successes — B             0
false successes — C             0
false successes — D             0
negative_control_pass            true
terminal_security_pass           true
strategy_exhausted_typed_pass    true
permanent_oracle_pass            true
irrecoverable_env_pass           true
```

This is stronger than the prior positive-only A/B benchmark: recovery does not turn permanent rejection, environment unavailability, strategy exhaustion, or a terminal security violation into a false successful completion.

## Control-integrity result

Across every A/B/C/D arm and every positive/negative scenario:

- recovery itself created no verified fact;
- `unsafe_retries = 0`;
- task-tool execution after a recovery transition remained Actor-mediated;
- the strict-isolation WRITE handler executed `0` times;
- no negative control was counted as successful completion.

```text
control_integrity_pass = true
benchmark all_passed   = true
```

## What the benchmark demonstrates

### 1. Automatic recovery has causal value inside the positive matrix

D completed 3/3 while A and the safety-preserving B comparator completed 0/3. The matched deterministic design therefore provides strong attribution **inside these constructed failure families** that the recovery path changes task outcome relative to stopping.

### 2. Typed routing is correct, but completion superiority over generic replan is not demonstrated

C and D both completed 3/3. Therefore this experiment does **not** support the stronger claim that typed routing improves completion rate over a competent generic full-replan policy.

What is demonstrated is narrower:

- the production router selected the intended `repair / observe / replan` action 3/3;
- targeted `repair` avoided one unnecessary diagnostic step and one tool call in `tool_repair`;
- no cost advantage appeared in the other two constructed cases.

The evidence supports **failure-type-specific routing as a potential efficiency/specificity optimization**, not a universal completion-rate advantage.

### 3. Negative controls reject false success

All four arms produced zero false completions across four negative controls. In particular, `strategy_exhausted` remained terminal and `terminal_security` never executed the unsafe handler.

## Discovered limitations / open findings

### A. Retry-only is under-exercised

The current positive matrix contains no emitted `retry_safe=true` failure, so B executes zero actual retries. A future benchmark expansion within the existing Stage05 remediation track should add at least one genuinely retry-safe transient failure if retry-only effectiveness itself needs to be compared. This does not require a new Stage.

### B. Irrecoverable cases are safe but not always recognized early

`irrecoverable_env_error` and `oracle_permanent_reject` do not falsely complete, but C and D continue until the hard 24-step budget. This is an important distinction:

- **safety property:** PASS — no false success, no unsafe retry;
- **termination-quality / efficiency property:** OPEN — the current recovery policy does not necessarily identify permanent irrecoverability early.

Thus the negative controls prove that recovery is bounded and cannot simply declare success, but they do **not** prove optimal early stopping.

### C. External validity remains limited

The benchmark has three deterministic recoverable failure families and four deterministic negative controls. It is not a natural task corpus, does not include stochastic model/controller variation, and does not estimate confidence intervals over repeated real-world tasks.

The 3/3 result must not be read as a 100% general recovery rate, and the single-step typed-routing saving must not be generalized into a universal efficiency claim.

## Validation environment

Fresh GitHub Actions run `31999746413`, verify job `95297707436`, on 2026-08-17:

- benchmarked implementation commit `5bcfb7e9e1df68cc0b05ece4139102dcaa4574a6`;
- Ubuntu `24.04.4` / `ubuntu-24.04` runner;
- CPython `3.11.15`;
- package `verified-state-harness 0.9.1`;
- pytest `209 passed, 5 skipped in 16.98s`;
- Stage05 A/B/C/D routing benchmark: `all_passed = true`;
- all other Stage03–08 and Stage02 remediation probes in `research-ci`: PASS.

## Disposition

**Benchmark gate: PASS.**

Claim-level disposition:

```text
Recovery vs stop                           PASS
Typed route selection correctness          PASS (3/3)
Typed vs generic completion superiority    NOT DEMONSTRATED (3/3 vs 3/3)
Typed vs generic cost benefit              OBSERVED, NARROW (1 step + 1 tool call total)
Negative-control false-success resistance  PASS (0 false successes across 4 controls)
Terminal security                          PASS
Early irrecoverable-case termination       OPEN
Broad real-world recovery effectiveness    OPEN
```

No new Stage is introduced by this benchmark expansion. It remains Stage05 recovery-effectiveness remediation/validation work on the existing research branch.
