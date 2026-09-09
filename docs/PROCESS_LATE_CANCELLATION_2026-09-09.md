# Idempotent Late Process Cancellation

## Situation
While investigating shell-to-loop delay, inspection of CrossSpawnSpawner showed that handle.kill() always attempted a platform kill, including after the process close signal had completed. The scope finalizer already checked completion, but the public kill path did not.

## Reason
Cancellation can arrive after normal or failed process termination. Reissuing a kill creates unnecessary OS work and can turn a completed operation into a process-not-found error. Checking at Effect construction time would still be incorrect if execution occurs later.

## Action
Added a Deferred completion check inside execution of the kill Effect. A completed handle now returns immediately. Running-child signal selection, escalation and process-tree handling remain unchanged.
Added three tests for repeated cancellation after successful exit, preservation of a non-zero exit code, and a kill Effect created before exit but executed after exit.

## Result
- Core typecheck: exit 0.
- Cross-spawn tests: 27 passed, 0 failed, 32 assertions, 8.14 seconds.
- Host typecheck: exit 0.
- Selected shell wait and queued-loop tests: 2 passed, 0 failed, 11 assertions, 22.20 seconds.
- No complete Host rerun.

## Evidence
These are developer regression results, not Harness Evidence or independent user acceptance.
The additional tests use real child processes and the existing spawner. They check repeated cancellation and preservation of exit state.
Machine-readable results: PROCESS_LATE_CANCELLATION_DIAGNOSTICS_2026-09-09.json.

## Residual Risk
This fixes a distinct late-cancellation defect; it does not establish the cause or resolution of either earlier timeout. No startup speed improvement is claimed.
The completion check does not eliminate every native exit/kill race before the close signal resolves.
POSIX-only branches in the existing tests are not executed on Windows, even where the test function returns successfully.
Actual OAuth/provider usage, full regression stability, native sandbox coverage and independent practical stability remain unproven.
No user settings, credentials, net_monitor.py, repository commit or push were changed.

