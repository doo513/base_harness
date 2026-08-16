# Stage 03 Final Logic / Integrity Re-review

## Verdict

**PASS / EXITED**, subject to the documented trust-boundary and single-writer assumptions.

## Re-review questions

### 1. Does checkpoint existence still get confused with resume correctness?

No. Resume now requires manifest, event chain, checkpoint envelope, event anchor, configuration match, and reconstructable state.

### 2. Can a stale or corrupted checkpoint be silently accepted?

No in the tested corruption/mismatch classes. JSON decode failure, envelope hash mismatch, state hash mismatch, run/manifest mismatch, missing anchor, and wrong anchor hash all fail closed.

### 3. Can a valid newer event be lost because checkpoint replacement did not happen before crash?

The event-first ordering allows a newer valid `state.snapshot` to be recovered. Resume rewrites the checkpoint to that event anchor.

### 4. Can replay perform an external action?

No. Replay is ledger validation plus state reconstruction only.

### 5. Can a committed non-idempotent action be executed twice after restart?

The tested path returns the COMMITTED receipt result and does not invoke the tool handler again.

### 6. What if the process dies after the external effect but before COMMITTED receipt persistence?

This is intentionally represented as PREPARED ambiguity. Automatic re-execution is blocked. This is a stronger and more accurate guarantee than claiming exactly-once without external transaction support.

### 7. Can resume run under a materially different configuration?

Not silently for the recorded fingerprint. The fingerprint includes goal/profile/verifiers/controller/model adapter/tool/security/budget/oracle information and source/provenance hashes where available.

### 8. Can model nondeterminism still change the future trajectory after resume?

Yes. Persistence reproduces the trusted prior state and configuration identity; it cannot force an external stochastic model to choose the same next token/decision unless the model/provider itself supports deterministic replay inputs and seed semantics.

### 9. Can an Actor forge checkpoint hashes?

Only if it can write the private run directory. SHA-256 envelopes are corruption/integrity-consistency checks, not authentication. Production use must preserve the Stage 02 filesystem boundary that keeps `run_dir` outside Actor access.

### 10. Can two runtimes safely write one run directory concurrently?

No. Stage 03 is single-writer. File locking/leases are not implemented and are explicitly outside this exit claim.

## Corrections made during final re-review

1. Added budget and verifier chain to configuration fingerprint.
2. Added profile/controller/verifier source hashes.
3. Added model adapter command hash.
4. Normalized non-idempotent ToolResult before both initial observation and receipt persistence.
5. Rejected stale/dirty run directories for new runs.
6. Strengthened replay from “latest snapshot lookup” to sequential validation of all `state.snapshot` transitions.
7. Added event-ahead checkpoint recovery test.
8. Added CLI resume test.
9. Reran Stage 02 real attack probe after Stage 03 changes.

## Final gates

```text
Stage 03 targeted tests        PASS (12)
Full regression               PASS (59)
Direct Stage 03 probe         PASS (4/4)
Duplicate external action     0
Stage 02 required attacks     PASS (12/12)
Stage 02 defense probes       PASS (4/4)
Compileall                    PASS
```
