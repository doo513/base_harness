# Host Git Discovery and Coordinator Status Fixture Repair

## Situation

The Host suite continued from the previous phase and terminated with exit 1 after 667 tests across 52 files in 227.82 seconds. Its five-failure stop was reached by one Git test and four Coordinator status tests. The formerly failing TUI configuration section had passed.

## Reason

A non-repository temporary directory inherited an ancestor checkout because Host test preload lacked the Git discovery ceiling already used by Core tests.

Coordinator status fixtures invoked persistent domain selection without a workspace. The current Host correctly requires a workspace for persisted session selection. Removing that requirement or granting Ready to make tests pass would weaken the product contract.

## Action

- Host preload appends the canonical OS temporary directory to GIT_CEILING_DIRECTORIES while preserving existing entries.
- A regression test asserts that canonical discovery ceiling.
- Coordinator status tests use disposable real temporary workspaces for the first domain-control request.
- A separate rejection test keeps SESSION_WORKSPACE_REQUIRED and inactive/non-Ready behavior explicit.
- Existing equality checks between operation responses, current status and status events remain in place.
- Production Git, Coordinator, verifier and Ready logic were not changed.
- Windows LOCALAPPDATA/APPDATA scratch isolation remains enabled.
- No repository commit or push was performed; net_monitor.py was not modified. Native Git commands in existing tests operate on disposable fixture repositories.

## Result

The targeted run passed 63 tests across six files, with 200 assertions in 23.58 seconds. Host typecheck exited 0. This includes the nine Git tests, five Coordinator status tests and previously repaired TUI/KernelHost/CLI/state-isolation coverage.

A new broader Host execution is running at the last observation. Its failure-collection cap is 20 instead of five to collect a larger batch without repeatedly paying for the same passing prefix. Per-test timeout remains 30 seconds. Neither execution is evidence of a full-suite pass.

## Evidence

- Completed prior Host log: .tools/validation/host-suite-after-tui-json-1788846781735.log
- Targeted log: .tools/validation/host-git-status-followup-1788847190160.log
- New broader Host log: .tools/validation/host-suite-expanded-1788847294624.log
- New live exec session: 89513. Poll this handle; do not restart merely because an observation times out.
- Companion summary: docs/HOST_GIT_STATUS_FIXTURE_DIAGNOSTICS_2026-09-08.json
- Changed files: runtime/packages/base-harness/test/preload.ts, test/test-state-isolation.test.ts and test/harness/coordinator-status.test.ts.

These records are developer diagnostics, not Harness Evidence or independent user validation.

## Residual Risk

GIT_CEILING_DIRECTORIES bounds native repository discovery in tests; it is not a filesystem sandbox or a production security boundary.

The broader Host suite remains incomplete. No claims are made about real provider accounts, genuine model task quality, native terminal coverage, platform isolation or standalone packaging.

The earlier non-isolated test run's potential effect on real user configuration remains unresolved. No original contents are known and no guessed restoration has been performed. This phase did not read or modify the user's credential files.
