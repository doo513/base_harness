# Stage 03 — Persistence / Resume / Reproducibility

## 1. Stage status

**PASS / EXITED**

Candidate/final version: `v0.4.0`

## 2. Objective

Move the harness from “checkpoint files are written” to a restartable execution model where:

- run identity survives process restart,
- checkpoint corruption is detected,
- event/checkpoint consistency is checked,
- committed non-idempotent actions are not replayed,
- ambiguous side-effect windows fail closed,
- replay produces the same canonical trusted-state hash,
- configuration/provenance drift is detected,
- resume is available through a public API and CLI.

## 3. Entry assumptions

Stage 02 was already PASS for the Linux namespace backend when its live runtime attestation succeeds.

Stage 03 assumes the persistence directory is a kernel-owned trust boundary. Hashes detect corruption and inconsistency; they are not a substitute for Stage 02 filesystem isolation against an attacker with write access to the run directory.

## 4. Failure model

Covered:

- hard process exit after a persisted transition,
- process death after non-idempotent receipt commit but before checkpoint advancement,
- PREPARED-only ambiguous action receipt,
- truncated/corrupted checkpoint,
- checkpoint/event anchor mismatch,
- event payload tampering,
- event ahead of checkpoint,
- task/config/budget drift,
- missing provenance,
- dirty run-directory reuse,
- public CLI restart.

Not claimed:

- multi-writer concurrency,
- distributed consensus,
- arbitrary external-system exactly-once delivery,
- migration/resume from the old unchained v0.3 event format,
- deterministic output from an intrinsically nondeterministic model.

## 5. Main implementation changes

### 5.1 `core/storage.py`

#### Before

`CheckpointStore` wrote plain JSON to a temporary path and renamed it.

#### After

Added:

- canonical JSON serializer
- canonical SHA-256 hashing
- fsync-backed atomic file replacement
- directory fsync after rename
- integrity envelope format
- `RunManifestStore`
- checkpoint schema v2
- checkpoint state hash
- manifest hash binding
- event sequence/hash anchor
- runtime metadata persistence
- `ReceiptStore`
- typed persistence/integrity/resume exceptions

Checkpoint body now binds:

```text
run_id
manifest_hash
event_seq
event_hash
state_hash
state
runtime_meta
```

### 5.2 `core/events.py`

#### Before

Each JSONL event was an independent object.

#### After

Each event contains:

```text
seq
prev_hash
kind
payload
step
ts
record_hash
```

`record_hash` covers all fields except itself. `prev_hash` creates a forward hash chain.

The event log now:

- verifies sequence continuity,
- verifies previous-hash continuity,
- verifies each record hash,
- detects malformed/truncated records,
- fsyncs after append,
- can locate the latest canonical `state.snapshot` event.

### 5.3 Runtime split — public resume lifecycle

Final module boundary:

- `core/runtime.py` — construction, kernel logging/failure accounting, run lifecycle
- `core/runtime_persistence.py` — manifest/checkpoint/replay/receipt/resume semantics
- `core/runtime_execution.py` — context, verification, completion, decision dispatch

The split was performed after the functional Stage 03 implementation to avoid leaving persistence and execution policy in one oversized runtime module. Full regression and direct probes were rerun after the split.

Added:

```python
HarnessRuntime.resume(...)
```

A resumed runtime:

1. verifies `run_manifest.json`,
2. verifies the event hash chain,
3. verifies checkpoint envelope/state hash,
4. verifies checkpoint → event anchor,
5. verifies manifest binding,
6. compares current configuration fingerprint with the persisted manifest,
7. restores the canonical state,
8. restores cumulative metrics/wall-time metadata,
9. resumes under the original `run_id`.

### 5.4 Event-ahead recovery

Transition persistence order is event-first, checkpoint-second.

If crash timing produces:

```text
latest valid state.snapshot seq > checkpoint.event_seq
```

resume verifies the newer event snapshot and rebuilds the checkpoint from it.

The inverse condition — checkpoint ahead of event ledger — is treated as integrity failure.

### 5.5 Canonical replay

`replay_state()` now walks the complete verified event chain and validates every `state.snapshot` transition:

- manifest hash must match,
- state hash must recompute correctly,
- state step must not regress.

`replay_state_hash()` hashes the resulting `HarnessState` snapshot.

This replay never executes tools or external effects.

### 5.6 Non-idempotent receipts

For `ToolSpec.idempotent == False`:

```text
stable action_id = H(run_id, step, tool, canonical args)
```

The runtime persists `PREPARED` before handler invocation and `COMMITTED` after the result returns.

Resume behavior:

| Receipt | Resume action |
|---|---|
| none | normal execution |
| COMMITTED | return recorded ToolResult; no handler invocation |
| PREPARED | halt/fail closed; do not execute automatically |
| different receipt already exists for same run/step | conflict/fail closed |

This provides **at-most-once automatic execution**, not universal exactly-once delivery.

### 5.7 Stable ToolResult replay

A defect was found during re-review: non-JSON Python objects could be stringified while writing the receipt, which meant first-run context and resumed context could observe different types.

Correction:

- normalize a non-idempotent ToolResult through the same JSON representation before it is exposed to the initial state/context,
- persist that normalized representation,
- reconstruct the same normalized `ToolResult` during receipt replay.

This makes first execution and receipt replay semantically consistent at the harness boundary.

### 5.8 Run manifest and provenance

`run_manifest.json` now records and integrity-binds:

- `run_id`
- harness/runtime version
- Python/platform
- task revision
- model revision
- goal/acceptance/constraints
- profile class + source hash
- verifier classes + source hashes
- minimum verification level
- controller class + source hash
- model adapter class/source hash
- model adapter command hash where available
- tool side-effect/idempotency/permission/provenance
- tool handler source hash where available
- sandbox backend name
- security configuration
- budget configuration
- oracle class/id/seal/backend/isolation requirement
- complete configuration hash
- provenance warnings

Resume rejects a changed configuration fingerprint.

### 5.9 Budget continuity

`Budget.hard_exceeded()` now accepts prior elapsed wall time. Checkpoints/state events preserve cumulative elapsed time, preventing a simple process restart from resetting the hard wall budget.

### 5.10 Dirty run-directory rejection

A new run requires an empty run directory. Existing persisted contents require explicit resume or a different directory.

### 5.11 CLI

Added:

```text
--resume
--task-revision
--model-revision
--require-complete-provenance
```

The CLI therefore exposes the same resume contract as the Python API.

## 6. Defects discovered during implementation and correction

### D3-01 — manifest config fingerprint initially omitted budget/verifier chain

**Problem:** a run could resume under a different budget or verification stack.

**Correction:** budget, profile/verifier identity, minimum verification level, oracle details, and source hashes were added to the configuration fingerprint.

### D3-02 — non-JSON ToolResult type drift

**Problem:** initial execution could observe a Python object while receipt replay observed its stringified JSON form.

**Correction:** both initial and replay paths now consume the same normalized JSON representation.

### D3-03 — model-command drift could be missed

**Problem:** if `model_revision` was omitted, changing a command-backed model while keeping `LLMController` could evade a class-name-only comparison.

**Correction:** model adapter source/class plus SHA-256 of its command string are included in the config fingerprint.

### D3-04 — stale run directory contamination

**Problem:** an existing directory with stale persistence artifacts could potentially be reused by a new run.

**Correction:** new run construction now requires an empty run directory.

### D3-05 — “replay” was initially too weak

**Problem:** using only the latest snapshot does not meaningfully validate the transition history.

**Correction:** replay now walks every hashed `state.snapshot`, validates its canonical hash, manifest binding, and monotonic step progression before returning the final state.

## 7. Tests added

`tests/test_stage3_persistence.py` contains 12 Stage 03 scenarios.

| ID | Scenario | Expected | Result |
|---|---|---|---|
| S3-01 | manifest/checkpoint/event binding | hashes/anchor consistent | PASS |
| S3-02 | truncated checkpoint | fail closed | PASS |
| S3-03 | resealed checkpoint with wrong event hash | anchor mismatch detected | PASS |
| S3-04 | task/config drift | resume rejected | PASS |
| S3-05 | event payload tampering | hash-chain failure | PASS |
| S3-06 | missing provenance | warning; strict mode failure | PASS |
| S3-07 | crash after receipt COMMITTED before state checkpoint | tool result deduplicated; effect count 1 | PASS |
| S3-08 | PREPARED-only receipt | halt; effect not replayed | PASS |
| S3-09 | real subprocess hard exit after persisted transition | resume; effect count 1 | PASS |
| S3-10 | event snapshot ahead of checkpoint | recover latest verified event state | PASS |
| S3-11 | budget drift + dirty run-dir | resume/new-run rejected | PASS |
| S3-12 | CLI `--resume` | same run id resumes | PASS |

## 8. Direct Stage 03 runtime probe

`scripts/stage3_resume_probe.py` performs four direct runtime scenarios outside pytest fixtures:

1. canonical replay hash
2. checkpoint corruption detection
3. real forced process exit + resume + duplicate effect count
4. PREPARED-only ambiguous side-effect fail-closed behavior

Observed summary:

```text
probe_count                4
passed_count               4
duplicate_external_actions 0
all_passed                 true
```

## 9. Regression results

Final local validation:

```text
Stage 03 tests:            12 passed
full pytest suite:         59 passed
compileall:                PASS
Stage 02 required probes:  12 / 12 PASS
Stage 02 defense probes:    4 / 4 PASS
```

## 10. Logic re-review

### Can Actor bypass trusted state through resume?

Not through the declared persistence API. Restored state must match the checkpoint hash, manifest, and anchored event snapshot. Production security still depends on the Stage 02 private run-directory boundary.

### Can replay re-execute external effects?

No. Replay reads and validates state snapshot events only. It never invokes tools.

### Can a committed non-idempotent action execute twice automatically?

The tested runtime path prevents it through COMMITTED receipt reuse.

### What happens in the unavoidable effect/receipt crash window?

If only PREPARED is durable, the harness cannot prove whether the external effect occurred. It halts instead of replaying the action.

### Can configuration silently change?

The manifest config fingerprint covers goal/profile/verifiers/controller/model adapter/tool/security/budget/oracle configuration. Resume rejects drift in the tested fields.

### Did Stage 03 weaken Stage 02?

No observed regression. The full test suite and real Stage 02 attack probe both remain PASS.

## 11. Unresolved risks / non-claims

1. **Hash envelopes are not signatures or MACs.** An attacker with write access to the private run directory could forge content and recompute hashes. Stage 02 isolation is therefore a dependency.
2. **Single writer only.** There is no file lock/distributed lease for two simultaneous runtimes using one run directory.
3. **No arbitrary exactly-once external transaction.** PREPARED-only ambiguity intentionally halts.
4. **No v0.3 persistence migration.** Old unhashed event logs are not silently accepted as v0.4 resume ledgers.
5. **Model determinism is not created by persistence.** Provenance and state are reproducible; an external model may still be stochastic.
6. **Filesystem durability is bounded by OS/filesystem semantics.** The implementation uses file fsync + atomic replace + directory fsync where available.

## 12. Exit criteria

| Criterion | Result |
|---|---|
| forced kill → resume succeeds | PASS |
| duplicate external action = 0 | PASS |
| checkpoint corruption demonstrated | PASS |
| event/checkpoint mismatch detected | PASS |
| event-ahead recovery demonstrated | PASS |
| deterministic replay state hash matches | PASS |
| run manifest exists | PASS |
| provenance drift/missing behavior demonstrated | PASS |
| public resume entry point | PASS |
| full regression | PASS |
| prior Stage 02 isolation regression | PASS |

## 13. Final verdict

```text
Stage 03 = PASS / EXITED
Version = v0.4.0
```

## 14. Next allowed stage

Stage 04 — Semantic Verification (`v0.5.0`).

Do not begin Stage 04 by weakening the Stage 03 receipt, manifest, event-chain, checkpoint, or resume invariants.

## 15. Commands executed for final evidence

```bash
# Baseline before Stage 03 implementation
PYTHONDONTWRITEBYTECODE=1 pytest -q
# observed: 47 passed

# Stage 03 targeted tests
PYTHONDONTWRITEBYTECODE=1 pytest -q tests/test_stage3_persistence.py
# observed: 12 passed

# Full regression
PYTHONDONTWRITEBYTECODE=1 pytest -q
# observed: 59 passed

# Direct Stage 03 durability probe
PYTHONPATH=src python scripts/stage3_resume_probe.py
# observed: 4/4 PASS, duplicate_external_actions=0

# Stage 02 real isolation regression
PYTHONPATH=src python scripts/stage2_attack_probe.py
# observed: required 12/12 PASS, defense-in-depth 4/4 PASS

# Syntax/import compilation
python -m compileall -q src tests scripts
# observed: exit 0 / PASS
```

Raw outputs are frozen under `evidence/`.
