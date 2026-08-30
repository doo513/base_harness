# 03. WorkGraph and Overlay Orchestration

## Situation

Subagent use depended on model choice, child scopes were not consistently bound to Claims, and workers could expose changes to the real workspace before independent verification.

## Reason

Parallelism is safe only when the Host validates the dependency graph, canonical path ownership, Claim coverage, and candidate base hashes before execution and commit.

## Action

- Added the flow `GoalContract -> adaptive exploration -> WorkGraph -> worker execution -> integration -> root verification`.
- Added `WorkUnit` Claim, Criterion, dependency, read-set, write-set, and integration ownership contracts.
- Limited implementation concurrency to two workers and queued additional units in FIFO order.
- Added copy-on-write worker Overlays and canonical path ownership checks.
- Rejected write/write and read/write conflicts from parallel scheduling.
- Denied worker shell/argv and out-of-ownership edits before I/O.
- Added candidate manifests containing before hashes, after hashes, revision, patch hash, and scope lineage.
- Added atomic commit with base-hash recheck, temporary sibling files, and rollback journal.

## Result

Worker success now means `candidate_ready`, not completion. Only a matching verifier attestation can commit the candidate, and workspace conflicts fail closed without overwriting external changes.

## Evidence

- Core orchestration and SecretRegistry: 5 tests passed.
- Coordinator queue and attested commit: 1 test passed.
- Mismatched attestation cannot commit.
- Changed base hashes block commit without overwriting the workspace.
- A third WorkUnit waits while two independent units execute.
