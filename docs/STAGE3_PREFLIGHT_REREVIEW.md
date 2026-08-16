# Stage 03 Preflight Re-review — Persistence / Resume / Reproducibility

## 1. Review scope

Stage 02 was treated as the current source of truth and re-reviewed before Stage 03 work began. The question was not whether checkpoint files existed, but whether the current kernel could survive interruption without corrupting trusted state or repeating already-observed side effects.

Reviewed boundaries:

- `HarnessRuntime` lifecycle and state ownership
- `CheckpointStore`
- `EventLog` / `JsonlLog`
- `ToolSpec.idempotent` and side-effect semantics
- run identity and configuration provenance
- budget/metrics continuity
- CLI public entry points
- Stage 02 isolation regression

## 2. Stage 02 regression verdict

No new defect was found that invalidated the Stage 02 exit decision.

Baseline before Stage 03 changes:

```text
pytest: 47 passed
Stage 02 production sandbox: previously PASS / EXITED
```

After Stage 03 implementation, the Stage 02 attack probe was rerun and still reported:

```text
required attacks:      12 / 12 PASS
defense-in-depth:       4 / 4 PASS
runtime attestation:   PASS / source=runtime_probe
workspace control:     PASS
```

Therefore Stage 03 was allowed to proceed.

## 3. Blocking Stage 03 defects found in the inherited implementation

### P3-01 — checkpoint save existed, resume did not

`CheckpointStore.save()` wrote JSON, but `HarnessRuntime.__init__()` always created:

- a new `run_id`
- a new empty `HarnessState`
- a new runtime lifecycle

There was no public restore path and no consistency check between checkpoint and event history.

**Impact:** checkpoint presence could be mistaken for resume correctness even though restart semantics did not exist.

### P3-02 — checkpoint integrity was not detectable

The inherited checkpoint had no schema version, state hash, manifest hash, or event anchor.

**Impact:** truncation, partial overwrite, stale checkpoint, or checkpoint/event mismatch could not be distinguished reliably.

### P3-03 — event log was append-only text, not an integrity ledger

Events had no sequence number, previous-record hash, or record hash.

**Impact:** deletion, modification, reordering, or truncation could not be detected by the harness.

### P3-04 — non-idempotent tool metadata was unused

`ToolSpec.idempotent` existed, but runtime execution did not use it.

**Impact:** a crash after an external effect but before state persistence could cause the same decision to be replayed after restart.

### P3-05 — no run manifest / provenance contract

The runtime did not freeze:

- task revision
- model revision
- controller/model adapter identity
- profile/verifier identity
- tool provenance
- security configuration
- budget configuration
- oracle identity
- runtime version

**Impact:** a resumed run could silently continue under a different configuration while appearing to be the same run.

### P3-06 — elapsed budget and metrics were process-local

`started_at` was recreated per process.

**Impact:** repeated restarts could reset the effective wall-time budget.

### P3-07 — run directory reuse was not fail-closed

A runtime could open an existing path and append/rewrite state without an explicit resume contract.

**Impact:** evidence from different runs could be mixed.

### P3-08 — no public CLI resume operation

There was no operator-facing `--resume` path.

## 4. Design decision before implementation

The Stage 03 implementation uses this durability ordering for a state transition:

```text
runtime actions/events
    ↓
append hashed state.snapshot event + fsync
    ↓
atomic checkpoint envelope write + fsync + rename + directory fsync
```

This deliberately makes the event ledger the first durable transition record. If a process dies after the event snapshot but before checkpoint replacement, resume may recover the newer verified event snapshot and rewrite the checkpoint.

For non-idempotent effects:

```text
PREPARED receipt (durable)
    ↓
execute tool
    ↓
COMMITTED receipt with normalized ToolResult (durable)
    ↓
state observation / transition persistence
```

Guarantee level:

- `COMMITTED` receipt: replay result, do not execute tool again.
- `PREPARED` only: execution is ambiguous; automatic replay is blocked.

The harness does **not** claim arbitrary exactly-once semantics for external systems. Without cooperation from the external service or a distributed transaction/idempotency key, the window between the real-world effect and the COMMITTED receipt cannot be resolved safely. The correct kernel behavior is fail-closed rather than duplicate the action.
