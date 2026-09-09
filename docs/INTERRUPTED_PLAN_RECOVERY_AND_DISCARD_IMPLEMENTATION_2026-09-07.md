# Interrupted Plan Recovery and Explicit Discard

Date: 2026-09-07
Implementation phases: 28 and 29
Status: Scoped recovery, typing and CLI/Host gates passed. Full product validation remains open.

## Situation

A persisted revise consumption marker caused pending-plan lookup to throw.
Kernel status hydration failed before the existing planning.discard control
could run, leaving a restarted session unable to discard its old revision.

The marker also could not establish whether its originating Host had exited.
Treating it as permission to replay a plan would risk competing with a live
writer or reusing previously consumed execution authority.

## Reason

Recovery must distinguish readable planning history from executable authority.
An explicit discard should let the user start a new plan, but a late result
from the previous writer must not publish the discarded revision.

A completed plan publication and its cancellation need one durable winner.
A stale latest-head cache must not lose a publication that already won.

## Action

- Added a read-only revision_pending preview with planOnly=true, awaiting_input, Ready disabled and a typed planning.discard recovery action.
- Ordinary requests, domain changes and execute remain rejected while that revision is unresolved.
- Added explicit discard without deleting or reversing the original consumption marker.
- Added a Host-owned revision claim and a signed, append-only publication/discard resolution bound to the previous reviewed-record digest.
- Used exclusive publication of complete files so publication and discard cannot both win.
- A per-claim publication intent prevents competing publishers from overwriting the same candidate revision.
- Signed resolution records recover a published successor even if reviewed.json still contains the prior head.
- Added optional revisionOf metadata while retaining reviewed-plan-v1, existing canonical plan files and verifier protocol v4.
- Clear discarded planning context and close a live unexecuted run before a new request; subsequent plans get fresh identity.
- Added TUI panel/footer guidance for /plan discard.
- Extended the real CLI fixture to pause a planning request, confirm the process is live, terminate it, restart the Host and exercise recovery.
- Corrected five TypeScript diagnostics in phase29 by explicitly typing the never-returning failure helper and the consume implementation return union; no runtime policy was weakened.

Changed implementation and validation files:

- [Reviewed-plan store](C:/Users/doo33/Downloads/base_harness/runtime/packages/kernel-host/src/reviewed-plan-store.ts)
- [KernelHost](C:/Users/doo33/Downloads/base_harness/runtime/packages/kernel-host/src/index.ts)
- [TUI recovery guidance](C:/Users/doo33/Downloads/base_harness/runtime/packages/tui/src/feature-plugins/verification.tsx)
- [Recovery tests](C:/Users/doo33/Downloads/base_harness/runtime/packages/kernel-host/test/reviewed-plan-recovery.test.ts)
- [Local model/MCP fixture](C:/Users/doo33/Downloads/base_harness/runtime/script/fixtures/local-runtime.ts)
- [Actual CLI/Host flow fixture](C:/Users/doo33/Downloads/base_harness/runtime/script/verify-headless-plan-flow.ts)

## Result

### Current gates

| Gate | Result |
| --- | --- |
| KernelHost suite | 52 tests passed; 218 expectations |
| Coordinator targeted suite | 17 tests passed; 189 expectations |
| Host routing and CLI output suite | 28 tests passed; 67 expectations |
| Total | 97 tests passed; 474 expectations; 0 failures |
| KernelHost, Coordinator, Host and TUI typechecks | All four passed |

Phase28 initially had five unique type diagnostics, reported to the user rather
than hidden behind passing runtime tests. Phase29 resolved them and reran the
scoped gates successfully.

### Actual execution

The phase28 local CLI case already passed forced interruption, restart,
explicit discard, fresh planning and standalone cross-directory execution
through actual independent-verifier Ready.

Phase29 exercised the attached Host paths:

| Flow | Client exit codes | Expected terminal result |
| --- | --- | --- |
| attached-interrupted | plan: 0; interrupted-revise: 143; pending-execute: 1; revise: 0; discarded-plan-execute: 1; wrong-plan: 1; execute: 0 | ready |
| attached-revision | plan: 0; revise: 0; wrong-plan: 1; execute: 0 | ready |
| attached-interrupted-provider-failure | plan: 0; interrupted-revise: 143; pending-execute: 1; revise: 0; discarded-plan-execute: 1; wrong-plan: 1; execute: 1 | blocked / model_provider_error |

Exit 143 is the deliberate interruption at the observed hold point, not a
deadline expiry. Rejected pending/discarded/wrong-plan executions returned
nonzero without additional model calls. Every client stayed within the
unchanged fixed deadline and emitted valid JSON lines.

Recovery did not create workspace output or Ready. The new plan used a new
plan ID and planning run, and only explicit execution started its execution
run. Both successful runs obtained actual verifier evidence. The Provider
failure produced model_provider_error, preserved verified worker output and
issued no Ready.

The ordinary, non-interrupted revision path also remained functional:
revision 2 retained its typed revisesPlan lineage and reached Ready.

## Evidence

- [Current gate exit codes](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase29-gates.json)
- [Attached flow batch](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase29-real-flows.json)
- [Local interruption recovery](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase28-local-interrupted.result.json)
- [Attached interruption recovery](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase29-attached-interrupted.result.json)
- [Ordinary attached revision](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase29-attached-revision.result.json)
- [Attached recovery with Provider failure](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase29-attached-interrupted-provider-failure.result.json)
- [Machine-readable handoff](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase29-handoff.json)

Validation used pinned Bun 1.3.14, the pinned local Python verifier, a local
model fixture and a local MCP fixture. No paid or external model calls were
made. Result files contain run/plan IDs, client logs, observed recovery status,
bounded traces and Ready artifact paths where applicable. Actual Ready
artifacts live under the recorded temporary workspaces.

## Residual Risk

- This is discard-and-rebuild recovery, not automatic resumption of an unfinished draft or interrupted worker.
- A pending marker does not prove another Host is dead. Discard revokes publication authority; it does not terminate another Host's in-flight model request.
- Concurrency gates were tested with the current implementation. Mixed old/new Host versions sharing the store are not supported; close older Hosts before using the new lifecycle.
- Exclusive complete-file publication requires filesystem hard-link support. Windows local filesystem behavior passed here; Linux and other filesystems were not newly validated.
- Same-OS-account access to the signing key remains outside the isolation guarantee.
- No new visual TUI, keyboard-navigation, CJK wrapping or terminal-restoration certification was performed. The added guidance is implemented and typechecked, not visually certified.
- Earlier intermittent waits did not recur in these cases. Their root cause is not proven solved.
- Timings are diagnostic observations, not a controlled performance benchmark. Added storage checks do not add an LLM review, but their latency impact has not been benchmarked.
- External OAuth/Provider behavior, full repository regression coverage and overall harness completion are not established by these scoped results.
- No git commands, commit or push were performed; net_monitor.py was untouched.

