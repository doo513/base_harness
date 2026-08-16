# Track F — Operational Extensions

Status: **CONDITIONAL / DEFER BY DEFAULT**

These items are not current Core correctness blockers. Implement only when workload/roadmap evidence makes the operational benefit concrete.

## F1. >64K mandatory contract externalization

Decision: **DEFER**.

Current `GoalContract` rejects oversized mandatory text before run creation instead of silently truncating authoritative semantics. No current workload evidence demonstrates that >64K contracts are a material blocker.

If real tasks hit the bound, use an authority-preserving design:

```text
ContractArtifact
  exact content digest
  immutable source identity
  section/clause index
  pinned critical constraints
  exact clause retrieval
```

The original artifact remains authority. A generated summary must never replace the authoritative contract.

## F2. Safe global orphan artifact GC

Decision: **CONDITIONAL**.

Stage08 transaction semantics prevent failed preparation artifacts from becoming authoritative, but unreferenced content-addressed blobs can consume storage. Correctness does not require immediate deletion.

If measured disk growth justifies GC, use conservative mark/rescan deletion:

1. scan every known durable run root/checkpoint/event reference source;
2. mark referenced artifacts;
3. list candidate unreferenced blobs;
4. enforce grace period;
5. produce dry-run inventory;
6. rescan all durable roots;
7. delete only candidates still unreferenced and older than grace threshold.

Never delete when:

- a run may be active;
- a reference source is unknown/unreadable;
- checkpoint/event metadata is corrupt;
- dependency/integrity status is uncertain.

Fail closed by retaining data.

## F3. Remote retrieval provenance / replay proof

Decision: **CONDITIONAL** — implement when a remote provider enters the roadmap.

A future remote receipt should minimally bind:

- request hash
- normalized query hash
- provider id/revision
- index revision if exposed
- response/content digest
- snapshot id / ETag if meaningful
- ranking policy
- retrieval timestamp as audit metadata

Resume should consume the original admitted local immutable artifact snapshot, not issue the remote query again merely to reconstruct state.

Keep these claims separate:

```text
provider honesty proven
!=
exact bytes consumed by the harness are replayable
```

The second can be guaranteed locally even when the first cannot.

## F4. Duplicate artifact integrity reads inside verification

Decision: **CONDITIONAL OPTIMIZATION**.

Current fail-closed chain can verify the same evidence once in `EvidenceRefVerifier` and again in a domain semantic verifier. This is conservative and correct, but can duplicate I/O for large artifacts.

Do not add a verified-buffer cache solely because the duplicate read exists. First measure realistic:

- evidence artifact size distribution;
- verification calls / solved task;
- bytes read / solved task;
- wall time contribution.

If material, a candidate optimization is a per-verification-attempt immutable verified-buffer map keyed by content address. Its lifetime must not extend beyond the verification attempt unless the integrity semantics are explicitly redefined.

## F5. Full fact dependency/version graph

Decision: **DEFER**.

Current event log preserves historical transitions and current state supports supersession markers. The Core Freeze audit fixed the reproduced stale same-key refuted marker. No remaining stale dependency failure has been reproduced that justifies a general dependency graph.

Add version/dependency machinery only after a concrete stale-state scenario shows that event history + current supersession is insufficient.
