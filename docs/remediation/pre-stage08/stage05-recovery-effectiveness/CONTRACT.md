# Contract — Stage05 Recovery Effectiveness A/B Benchmark

Status: **FROZEN before benchmark implementation**

Finding: `O05-001`

## Question

Under matched deterministic failure-injection tasks, does the existing Stage05 recovery-control mechanism allow the same Actor policy to recover and complete tasks that a no-recovery fail-closed baseline cannot complete, and what deterministic step/tool/failure cost does that intervention add?

This benchmark does **not** ask whether Recovery universally improves arbitrary LLM tasks.

## A/B definitions

### A — Recovery enabled

Use the production `FailureRouter` and `HarnessRuntime` recovery transition path unchanged.

### B — No-recovery baseline

Use the same HarnessRuntime, task, controller, tools, oracle and budget, but route the first nonterminal injected task failure to `CHECKPOINT_STOP` instead of giving the Actor a repair/observe/replan/rollback directive.

Terminal safety failures remain terminal in both arms. The baseline is intentionally conservative: it represents “do not attempt automatic recovery,” not an unsafe retry policy.

## Matched-task rules

Each pair must have identical:

- goal/acceptance;
- controller code and initial controller state;
- tool implementations and initial environment state;
- budget;
- task revision family;
- injected failure point and failure payload;
- completion oracle.

Only the failure-routing policy may differ.

## Required scenarios

At minimum three deterministic recovery-relevant families:

1. **tool repair** — primary tool path fails; recovery directive permits Actor to choose an alternate successful path;
2. **missing information / observe** — first path lacks required information; observe directive permits an evidence-gathering action before success;
3. **verification/replan** — initial completion or claim path is rejected; replan directive permits a different task path that can satisfy the oracle.

A terminal security/persistence control case must also show that the benchmark does not count unsafe continuation as effectiveness.

## Required metrics

Per arm and scenario:

- completed / halted;
- persisted steps;
- Actor decisions;
- tool calls;
- failures;
- recovery transitions;
- strategy switches;
- oracle checks;
- repeated failure count;
- unsafe retries.

Aggregate:

- completion rate;
- completion-rate delta A-B;
- successful-pair count;
- additional steps/tool calls per recovered success;
- safety-regression count.

Wall time may be recorded but is not a correctness/effectiveness gate.

## Success criteria

The controlled benchmark is PASS only if:

- at least 3 matched recoverable scenarios are executed;
- Recovery-enabled completes strictly more recoverable scenarios than the no-recovery baseline;
- every enabled-arm completion is accepted by the same independent task oracle used by its baseline pair;
- no enabled-arm success requires direct recovery mutation of verified facts or direct recovery tool execution;
- terminal safety cases do not continue automatically;
- existing Stage03–08 regression/probes remain green.

## Interpretation boundary

A PASS closes only: **“Recovery has demonstrated positive causal utility on the frozen deterministic benchmark.”**

It does not close:

- broad real-world LLM/agent effectiveness;
- performance across unknown models/domains;
- statistical significance on a natural task corpus.

If the benchmark is too constructed to support broader claims, `O05-001` must become PARTIAL rather than CLOSED.
