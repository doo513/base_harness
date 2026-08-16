# 05 — Validation Gates

## Gate A — Truth Integrity
Actor cannot create trusted facts or completion; unverified claims cannot enter trusted state; evidence strength/relevance required.

## Gate B — Execution Integrity
Non-zero != success; permissions/confirm/pre/post enforced; malformed actions do not crash; actor cannot mutate harness-private state; real isolation required where claimed.

## Gate C — Oracle Integrity
Acceptance assets sealed/hash-checked; actor cannot modify criteria; provenance recorded; post-evaluation integrity checked.

## Gate D — Persistence Integrity
Atomic save; actual resume; duplicate side-effect prevention; corruption handling; state/event consistency.

## Gate E — Reproducibility
Record harness SHA, model/version, prompt/config hash, runtime/container digest, task revision/hash, seed, timeout, budgets, tool calls, event log, artifact hashes.

## Gate F — Benchmark Validity
Baseline, ablation, repeated runs, dispersion/CI, hidden tasks where possible, false completion, verifier FP/FN, state corruption, cost/time/tool metrics.
