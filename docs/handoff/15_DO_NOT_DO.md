# 15 — Do Not Do

## Do not add complexity before evidence

Do not add:
- RAG
- vector DB
- memory graph
- multi-agent swarm
- planner hierarchy
- automatic skill learning
- model router

unless the active stage explicitly requires it.

## Do not confuse concepts

```text
Memory != State
RAG != Resume
Observation != Fact
Evidence existence != Evidence sufficiency
Read-only verifier != Correct verifier
Deterministic oracle != Perfect oracle
Checkpoint file != Resume semantics
Mock sandbox != Production sandbox
```

## Do not overclaim

Avoid:
- "proven universal"
- "best harness"
- "solved verification"
- "secure sandbox"
- "external oracle guaranteed"

unless evidence supports the exact claim.

## Do not silently rewrite history

Keep failed tests and earlier stage evidence.
Use errata or later-stage corrections.

## Do not allow the actor to own truth

Actor may:
- propose
- act
- request completion

Actor may not:
- commit trusted fact
- modify sealed oracle
- set completion directly

## Stage 03 persistence rules

Do not claim:

- `PREPARED` receipt means the external effect did not happen,
- local receipts create universal exactly-once delivery,
- an unkeyed SHA-256 envelope authenticates data against a writer who can modify `run_dir`,
- replay may safely re-execute tools,
- a v0.3 unhashed event log is automatically a valid v0.4 resume ledger.

Do not resume under silently changed task/model/tool/verifier/security/budget/oracle configuration.
