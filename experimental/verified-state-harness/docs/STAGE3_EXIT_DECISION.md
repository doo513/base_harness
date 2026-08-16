# Stage 03 Exit Decision

## Decision

```text
Stage 03 — Persistence / Resume / Reproducibility
PASS / EXITED
```

Promoted version: `v0.4.0`

## Required exit evidence

| Exit condition | Evidence | Result |
|---|---|---|
| forced kill → resume | subprocess exit 73 + restored same run | PASS |
| duplicate external action = 0 | effect ledger contains one `ONCE` | PASS |
| checkpoint corruption behavior | truncated checkpoint | PASS / fail closed |
| event/checkpoint mismatch | wrong anchored hash | PASS / fail closed |
| deterministic replay hash | canonical replay vs checkpoint state hash | MATCH |
| configuration provenance | run manifest + config hash | PASS |
| missing provenance behavior | warning + strict failure | PASS |
| public resume | Python API + CLI | PASS |
| regression | 59 tests | PASS |
| Stage 02 isolation | attack probe rerun | PASS |

## Important semantic limitation

Stage 03 provides durable **at-most-once automatic execution** for non-idempotent calls.

It does not claim that an arbitrary external system participates in an exactly-once transaction. A PREPARED-only receipt is an ambiguous state and blocks automatic replay.

## Next allowed stage

Stage 04 — Semantic Verification (`v0.5.0`).
