# Host Regression After Deferred Location Loading

## Situation
The deferred location-runtime import change passed Core and Host typechecks, four graph tests and 23 targeted ACP tests. A complete Host run was required to check the existing full-suite ACP initialize failure.

## Reason
Isolated success does not establish full-suite or practical stability. The full run was executed once with the existing Bun 1.3.14 command, fixture configuration, per-test deadlines and unsupported-symlink reporting unchanged.

## Action
- Ran the complete Host suite once and waited for the same process to terminate.
- Re-ran the shell-wait and queued-loop tests in isolation after the full suite finished.
- Added diagnostic-only stage tracking to the failing shell-wait test; did not change its 10-second deadline, shell command, verification policy or assertions.
- Re-ran those two tests and Host typecheck.
- Did not run paid model requests, Git commands or modify net_monitor.py.

## Result
Full Host: exit 1; 3274 passed, 60 skipped, 1 todo, 2 failed; 3337 tests across 253 files; 45 snapshots; 8856 assertions; 2074.43 seconds.

Remaining failures:
1. test/cli/acp/config-options.test.ts: model option is listed with category "model". The actual timeout is request:initialize, not model listing. It produced no protocol output within 15059 ms.
2. test/session/prompt.test.ts: loop waits while shell runs and starts after shell exits. It exceeded the existing 10000 ms deadline.

The shell-wait failure reproduced in isolation, while shell completion resumes queued loop callers passed. The two-test run before instrumentation took 25.85 seconds; the instrumented run took 24.11 seconds. Both reported 1 pass, 1 fail and 11 assertions. The runner reported cleanup of one dangling process.
Host typecheck after diagnostic instrumentation exited 0.

## Evidence
All artifacts in this report are developer diagnostics, not Harness Evidence or independent user validation.
The ACP child recorded cli.modules_ready at 1025 ms and runtime.import_start at 1269 ms. No runtime.modules_ready marker appeared before the timeout. The deferred import change has NOT resolved the complete-suite failure.
The new shell diagnostic did not emit a phase report before process termination. This does not prove whether setup, the test body or teardown consumed the timeout; phase attribution remains unknown.
The complete run finished before the test-only diagnostic change; it is not a full-suite validation of that subsequent instrumentation.
Machine-readable results: HOST_DEFERRED_LOCATION_REGRESSION_DIAGNOSTICS_2026-09-09.json.

## Residual Risk
- The prior ACP timeout remains open.
- The additional shell timeout is reproducible, but its cause and relationship to the latest runtime change are not established.
- Test-body finalizer diagnostics alone are insufficient for the observed timeout. Next investigation should cover fixture setup and runner cancellation/teardown boundaries before modifying execution logic.
- Do not increase deadlines, relabel failures as skips or repeat the full suite without a focused hypothesis.
- Windows symlink skips are unsupported capabilities, not passing security checks.
- Real OAuth/provider use, independent acceptance and prolonged practical stability remain unverified.

