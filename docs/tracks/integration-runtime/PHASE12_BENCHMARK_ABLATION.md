# Phase 12 — Benchmark / Ablation Infrastructure

Status: INFRASTRUCTURE IMPLEMENTED; no real performance claim is made.

## Problem / evidence

The post-Stage08 evaluation track already states that deterministic probes prove mechanisms, not that the harness improves real tasks enough to justify cost. A valid harness-vs-baseline comparison must keep task, model, tools, budget, oracle, and environment matched.

## Contract

Every evaluation record must bind the following controls:

- task ID and task revision;
- model/provider revision;
- domain profile;
- toolset revision;
- budget revision;
- oracle revision;
- environment revision.

Ablation aggregation fails closed when those control fingerprints differ. The `arm` field is the experimental variable and is deliberately excluded from the matched-control fingerprint.

## Implementation

- added `EvaluationControl` and deterministic control fingerprinting;
- added `EvaluationRecord` with solve/completion/tool/failure/model-token/model-latency/wall-time fields;
- `EvaluationRecord.from_runtime()` can capture existing Runtime metrics plus Model Gateway telemetry when the caller owns both objects;
- added integrity-checked JSONL load/append helpers;
- added `MatchedAblationReport` that rejects mismatched controls and duplicate arm/repeat pairs;
- aggregate output includes solve rate, false completion requests, average steps/tool calls/failures/tokens/model requests/model latency/wall time;
- added `scripts/summarize_ablation.py` for reproducible report generation.

## Structural review

- evaluation data has no runtime truth/progress/completion authority;
- comparison refuses silent model/task/tool/budget/oracle/environment drift;
- provider token/latency metrics come from the Model Gateway telemetry object rather than being inferred from text;
- baseline/harness arm labels do not alter runtime behavior by themselves;
- report generation is deterministic for a fixed record set.

## Validation focus

`tests/test_integration_evaluation.py` covers:

- matched-control drift rejection;
- repeated-arm solve/token aggregation;
- JSONL round trip;
- control fingerprint tamper rejection.

## Performance-claim gate

No performance claim is made by this phase. The report field named `performance_claim_allowed` is only a minimal structural indicator that more than one arm and repeat are present; it is **not** statistical or external-validity evidence. An actual claim still requires the Real Evaluation track conditions: representative real corpus, repeated runs, matched controls, preserved raw evidence, and appropriate uncertainty analysis.

## Next evidence

Use Phase 11 live cases to produce repeated records for at least Software and Hackathon/development-relevant task families, then compare incremental arms such as:

1. model + raw tools baseline;
2. + verified-state Kernel;
3. + Agent Control;
4. + structured tools/context relevance;
5. + project memory/domain workflow.

Only then tune no-progress thresholds or justify feature cost.
