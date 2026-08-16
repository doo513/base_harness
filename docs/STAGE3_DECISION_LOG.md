# Stage 03 Decision Log

## D-01 — Event-first, checkpoint-second transition persistence

**Decision:** fsync the canonical `state.snapshot` event before replacing the checkpoint.

**Reason:** if the process dies between the two writes, the event ledger may safely be ahead and resume can rebuild the checkpoint. A checkpoint that claims a state not present in the ledger is not accepted.

## D-02 — Use hash chaining for event consistency

**Decision:** add `seq`, `prev_hash`, and `record_hash` to every kernel event.

**Reason:** plain append-only JSONL does not prove order or tamper absence.

## D-03 — Store full canonical state snapshots as replay transitions

**Decision:** persist verified canonical state snapshots in the event ledger and validate all snapshots during replay.

**Reason:** Stage 03 needs deterministic trusted-state reconstruction without executing side effects. This is deliberately simpler than building a domain-event reducer before semantic stages are complete.

## D-04 — Do not claim arbitrary exactly-once external actions

**Decision:** implement PREPARED/COMMITTED receipts and at-most-once automatic replay semantics.

**Reason:** local persistence cannot atomically commit an arbitrary remote side effect and a local receipt. PREPARED-only is therefore ambiguous and must halt rather than retry.

## D-05 — Normalize non-idempotent ToolResult before first observation

**Decision:** both initial execution and receipt replay consume the same JSON-normalized result.

**Reason:** otherwise a Python object may be converted to a string only on persisted replay, causing context drift.

## D-06 — Bind resume to configuration provenance

**Decision:** freeze goal/profile/verifier/controller/model-adapter/tool/security/budget/oracle configuration in a manifest hash.

**Reason:** restoring state under a different verifier, tool policy, budget, or model adapter is not the same run.

## D-07 — Source hashes supplement explicit revision fields

**Decision:** record source hashes where Python source is inspectable and a command hash for command-backed model adapters.

**Reason:** class names alone are too weak to detect implementation drift. Explicit task/model revisions remain the preferred external provenance.

## D-08 — New runs require empty run directories

**Decision:** do not merge new-run output with stale persistence artifacts.

**Reason:** an explicit `resume` operation must be the only path that consumes old state.

## D-09 — Preserve cumulative wall budget across restart

**Decision:** persist elapsed wall time and include it in future budget checks.

**Reason:** restart must not become a mechanism for resetting hard execution limits.

## D-10 — Stage 03 PASS depends on the Stage 02 private persistence boundary

**Decision:** use SHA-256 envelopes for consistency/corruption detection, not as an authentication claim.

**Reason:** an Actor that can write `run_dir` could rewrite data and recompute unkeyed hashes. Production integrity therefore depends on Stage 02 keeping private harness state outside Actor write access.


## D-11 — Split runtime persistence from execution policy before push

**Decision:** extract Stage 03 persistence/resume methods into `runtime_persistence.py` and decision/verification execution methods into `runtime_execution.py`, leaving `runtime.py` as the lifecycle/composition layer.

**Reason:** the completed Stage 03 implementation had grown `runtime.py` into a mixed-responsibility module. The split preserves behavior while making the persistence trust boundary and future semantic-verification work independently reviewable. The full 59-test suite, Stage 03 direct probe, and Stage 02 attack regression were rerun after this refactor.
