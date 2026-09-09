# Compaction Cancellation and Snapshot Cost Repair

## Situation
The retry-backoff cancellation test failed in a fresh isolated run: 379 ms against the existing 250 ms threshold, despite interruption reaching the fiber.

## Reason
- Processor creation, step handling, and finalization snapshot the workspace even for Host-generated tool-free compaction summaries.
- The interruption handler wrapped only an individual model stream, leaving interruption during the retry schedule outside its status/error recording boundary.
- Increasing the test threshold would neither remove unnecessary I/O nor correct cancellation state.

## Action
- Skipped initial and per-step workspace snapshots for Host-generated summary messages.
- Preserved pre-stream snapshot capture for ordinary execution, including tools that run before their first stream event.
- Moved interruption handling outside the retry schedule so it covers stream execution and backoff.
- Retained awaited cleanup and the existing 250 ms cancellation threshold.
- Added assertions for zero extra model retries, final idle status, persisted aborted summary error, and completion timestamp.
- Added a summary fixture whose Snapshot service fails on any track/patch call.

## Result
- Fresh pre-change reproduction: 0 passed, 1 failed, 55 filtered out; measured 379 ms against 250 ms.
- Targeted cancellation/setup/no-snapshot tests: 3 passed, 0 failed, 54 filtered out, 14 assertions, 10.88 seconds.
- Host typecheck passed.
- Full compaction plus ordinary tool snapshot-race regression: 57 passed, 1 skipped, 0 failed, 183 assertions, 58 cases across 2 files, 39.28 seconds.
- The known compaction cancellation failure is resolved in these runs without relaxing its threshold.
- Ordinary tool-execution snapshot race remains covered and passed.

## Evidence
- Baseline session 45842 exited 1 with the 379 ms assertion.
- Targeted tests/typecheck session 62446 ended with COMPACTION_ABORT_GATE tests=0 typecheck=0.
- Full regression session 87173: PID 9412, stopped=true, timedOut=false, exitCode=0.
- Stdout: .tools/validation/compaction-and-snapshot-regression-1788861694137.stdout.log.
- Stderr: .tools/validation/compaction-and-snapshot-regression-1788861694137.stderr.log.
- Companion: COMPACTION_ABORT_SNAPSHOT_DIAGNOSTICS_2026-09-08.json.

## Residual Risk
- A successful 250 ms fixture run is not a latency percentile guarantee on every machine or under contention.
- Persisting cancellation state and awaited cleanup still have real I/O costs.
- The no-snapshot optimization is restricted to Host-generated tool-free summaries, not arbitrary read-only actors or normal execution.
- The two known Windows symlink failures remain, along with full-suite and real-user validation.
- The broader Host prompt suite last passed before this processor change; a later full regression is still required.
- No paid model calls, repository Git operations, net_monitor.py edits, or watchdog tree-kill exercise were performed.

