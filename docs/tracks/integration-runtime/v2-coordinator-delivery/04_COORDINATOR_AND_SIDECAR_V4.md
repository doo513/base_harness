# 04. Coordinator and Sidecar Protocol v4

## Situation

TUI and headless execution separately managed verifier state, worker completion committed too early, child verification was not authoritative, and repair behavior differed by interface.

## Reason

GoalContract, WorkGraph, worker queue, verifier lifecycle, candidate commit, repair routing, and final Ready require one Host owner.

## Action

- Added `@base-harness/coordinator` as the single Host state-machine owner.
- Added phases for scheduling, candidate verification, commit, integration, root verification, repair, blocked, and interrupted states.
- Added sidecar protocol v4 requests for candidate attachment, candidate commit, and scope reopen.
- Materialized candidates under the harness state root and ran candidate verifiers with that workspace as `cwd`.
- Required attestation equality for candidate ID, candidate revision, and patch hash.
- Preserved worker Overlay and child session across local repair revisions.
- Limited identical failure repair to the configured count and isolated `repair_exhausted` to the owning scope.
- Added root integration continuation and root-local repair for both WorkGraph and direct tasks.
- Waited for active workers, queued workers, and root integration before completion verification.

## Result

TUI, headless, and attach modes now observe the same Coordinator status. Child scopes can issue only `scope_verified`; final Ready remains root-only and fail-closed on verifier/protocol failure.

## Evidence

- Protocol v4 verification client tests passed.
- Protocol v3 sidecar execution is rejected while historical v2/v3 artifacts remain readable.
- Candidate workspace paths must resolve under the harness state root.
- Candidate temporary workspaces are removed after verification, commit, or discard.
- Provider, protocol, verifier, and workspace failures are not sent to implementation repair.
