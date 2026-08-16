# Stage 06 — Preflight Logic / Implementation / Structure Re-review

Status: **ENTRY REVIEW COMPLETE**

Base release: `v0.6.0`

Branch: `research/verified-state-stage03`

## Objective

Re-read the Stage 05 release as the substrate for Loop / Progress Control before adding any Stage 06 implementation. The purpose is to identify defects that would make a progress detector unsound or would cause it to weaken an earlier Stage guarantee.

## Findings

### P6-01 — Artifact reference growth is not evidence novelty

Severity if implemented naively: **HIGH**.

`_store_tool_observation()` names artifacts with the current step. `ArtifactStore.put_text()` constructs the reference from `sha256(content) + '_' + safe_name`.

Therefore the same tool result bytes recorded at different steps produce different artifact references even when the content digest is identical. Counting new refs would allow repeated identical work to appear productive forever.

Required correction: Stage 06 compares verified **content digests**, not ref strings.

### P6-02 — Speculative state is Actor-controlled

Severity if implemented naively: **HIGH**.

`propose` and `refute` directly mutate hypothesis/refutation state after Decision validation. Treating those mutations as authoritative progress would let the Actor reset loop counters by generating speculative churn.

Required correction: speculative changes may be audited as activity but do not independently reset progress windows.

### P6-03 — Exact payload identity alone is loop-evasion prone

Severity: **HIGH**.

If repetition identity hashes the entire Actor payload, changing whitespace, narrative reason text, or irrelevant argument formatting creates a new signature without changing the underlying action family.

Required correction: maintain both normalized exact identity and a coarse family identity. Progress is not inferred from signature novelty.

### P6-04 — Family identity alone can create false positives

Severity: **MEDIUM**.

Treating every call to one tool as identical would block legitimate retries that produce new evidence.

Required correction: family repetition only matters when the decision produced no recognized verified/evidence progress.

### P6-05 — Specific failures must outrank generic no-progress

Severity: **CRITICAL** if violated.

A tool/verification/security/persistence decision may already schedule a Stage 05 recovery. Scheduling `NO_PROGRESS` afterward would supersede the pending transition and could replace a terminal security/persistence route with a weaker recovery.

Required correction: if a Decision already created a pending recovery, Stage 06 records no additional no-progress failure for that Decision.

### P6-06 — Recovery steps are not Actor progress samples

Severity: **HIGH**.

Stage 05 recovery transitions consume normal harness steps, but they do not consume an Actor decision. Counting them as no-progress would cause recovery itself to accelerate loop escalation.

Required correction: only Actor Decision dispatches are evaluated by the progress detector.

### P6-07 — Progress state must be replayable

Severity: **HIGH**.

No Stage 06 state exists in the current `HarnessState` snapshot. Any in-memory-only counter would reset on resume and allow loops to evade thresholds through interruption.

Required correction: durable progress counters are part of `HarnessState.snapshot()/from_snapshot()`.

### P6-08 — Progress policy is execution semantics

Severity: **HIGH**.

Thresholds and classification policy determine whether the runtime continues or escalates. If they are not included in the manifest configuration descriptor, the same persisted run could resume under different loop semantics.

Required correction: progress policy descriptor participates in Stage 03/04 provenance fingerprinting.

### P6-09 — New progress checkpoints can create a controller/step split

Severity: **HIGH**.

Persisting progress immediately after a successful Actor decision but before the existing outer-loop step increment would checkpoint the advanced controller cursor and state at the old step. A crash in that window would change replay semantics.

Required correction: ordinary progress state rides the existing actor-step checkpoint. Only Stage 05 `fail()` keeps its existing immediate recovery scheduling commit point.

### P6-10 — Failed outputs must not manufacture progress

Severity: **HIGH**.

Tool failures already enter Stage 05 recovery and their error strings may contain volatile values. Counting changing failed-output bytes as evidence novelty would conflict with the typed failure path.

Required correction: only successful observations are candidates for evidence-novelty progress.

### P6-11 — Strategy switch is not progress

Severity: **MEDIUM**.

`SWITCH_STRATEGY` increments a durable generation. If generation change itself reset the last-progress horizon, repeated empty strategy switches could continue indefinitely until only the hard budget stopped them.

Required correction: local repetition counters reset on generation change, but last actual progress generation does not.

### P6-12 — Evidence integrity must be checked before progress recognition

Severity: **CRITICAL** if violated.

Artifact references are content addressed, but simply reading the digest prefix without checking current bytes would allow a tampered artifact to remain a progress signal.

Required correction: Stage 06 recomputes SHA-256 from the artifact bytes and compares it to the encoded digest. Mismatch enters the existing persistence/integrity failure path.

## Entry decision

No finding requires reopening Stage 01–05. These are Stage 06 design constraints rather than regressions in the released Stage 05 guarantee.

**Stage 06 implementation may proceed only under the frozen Progress Contract.**
