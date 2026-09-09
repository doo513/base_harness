# Full Host Regression: Complete Inventory

## Situation
The earlier Host run stopped after 20 failures and did not establish the state of the remaining tests. Scoped fixes were followed by a full run without early failure bail or snapshot update mode.

## Action
- Ran bundled Bun 1.3.14 over the complete Host test discovery.
- Preserved the original process throughout an observation-host interruption; no runtime or test source changed while it ran.
- Kept Windows snapshot symlink capability skips visible and unverified.
- Collected the complete failure inventory after terminal exit.
- Re-ran the WebSocket timeout case and its entire test file in fresh processes without changing code.

## Result
- Full run: 3247 passed, 55 skipped, 1 todo, 16 failed, 1 additional error.
- 3319 reported cases across 250 files; 8648 assertions.
- Snapshots: 16 passed, 1 failed.
- Exit code: 1. Full validation did not pass.
- Reported duration: 6707.43 seconds. One WebSocket case reported 4850716.13 ms against its 30000 ms limit. Do not use this anomalous run as a performance benchmark.
- Isolated WebSocket case: 1 passed, 0 failed, 5 assertions, 4.34 seconds.
- Complete isolated WebSocket file: 31 passed, 0 failed, 145 assertions, 4.05 seconds.
- The WebSocket failure did not reproduce in these fresh runs; its original cause remains unconfirmed.

## Failure Groups
- Native symlink setup: 5 failures across filesystem, glob, and editor-context fixtures.
- TUI branding expectations: 4 failures expecting opencode names instead of base-harness.
- CLI help snapshot: 1 failure requiring source/contract comparison.
- ACP subprocess behavior: 3 failures involving model options, stdin EOF, and prompt resources.
- WebSocket timing, external-path shell test, and truncation fresh-process startup: 3 failures.
- An additional process error followed the truncation timeout.

## Evidence
- Full run session 56927 is terminal with exit code 1; do not poll it again.
- Log: .tools/validation/host-full-regression-1788862363863.log.
- Command: $env:BASE_HARNESS_DISABLE_MODELS_FETCH='true'; $env:BASE_HARNESS_PYTHON='C:\Users\doo33\Downloads\base_harness\.tools\verifier\Scripts\python.exe'; & 'C:\Users\doo33\Downloads\base_harness\.tools\bun-1.3.14\bun.exe' test --timeout 30000 --only-failures 2>&1 | Tee-Object -FilePath 'C:\Users\doo33\Downloads\base_harness\.tools\validation\host-full-regression-1788862363863.log'; exit $LASTEXITCODE.
- Companion status and complete titles: HOST_FULL_REGRESSION_STATUS_2026-09-08.json.

## Residual Risk
- Passing isolated tests does not erase the failed full run or prove absence of order/resource/timing interactions.
- The five newly visible symlink failures are not repaired by the snapshot-specific capability handling.
- No automatic skip widening, timeout increase, runtime fallback change, or snapshot rebaseline was applied to these newly observed failures.
- ACP failures and subprocess startup delays need isolated reproduction with bounded cleanup.
- Full post-isolation Core regression is still pending.
- Real-account OAuth, long-running TUI use, cross-platform sandbox behavior, native symlink promotion, and independent user stability remain unproven.

