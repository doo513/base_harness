# Host Test Isolation Repair and TUI Configuration Failure Discovery

## Situation

The broader Host suite was started with Bun 1.3.14, a 30-second per-test timeout and a five-failure stop. It ran 456 tests across 37 files in 119.95 seconds before stopping. This was not a full-suite pass.

During execution, logs showed the actual Windows LOCALAPPDATA/base-harness configuration path. Host test preload isolated XDG locations but not LOCALAPPDATA. Core Global paths use LOCALAPPDATA on Windows.

## Reason

Test infrastructure must not use developer configuration as scratch state. The configuration fixtures write and remove global configuration files, so this was a concrete safety defect, not merely possible test contamination.

Other initial failures included a legacy KernelHost fixture lacking the required fresh execution-run handoff and outdated product-name expectations. Production admission checks must not be weakened to satisfy these fixtures.

## Action

- Host preload now sets LOCALAPPDATA and APPDATA to process-owned scratch paths before application imports.
- Inherited explicit configuration paths, inline config and inline auth overrides are removed from the test process.
- A preload assertion rejects global data, cache, config or state paths outside the scratch root before projectors and tests load.
- The test cache marker now follows current Base Harness platform paths.
- A dedicated test asserts scratch confinement of writable global paths.
- The KernelHost fixture now proves missing execution support is rejected without consuming the plan or changing input content, then verifies handoff to a different execution run before graph acceptance.
- CLI model-list advice and the default attention sound-pack expectation use the current Base Harness names.
- No production verifier, completion gate, model identifiers or migration policy was changed.
- No Git operation was performed; net_monitor.py was not modified.

## Result

The isolated targeted run completed 45 tests: 25 passed, 20 failed, 107 assertions, 24.47 seconds. Host typecheck passed. All remaining failures in this run are in the TUI configuration test file.

The nine KernelHost, CLI-error and state-isolation tests passed. The complete targeted gate remains failed.

A concrete implementation mismatch was found after the edit phase: ConfigPaths.files searches only a name.jsonc file. However, fileInDirectory supports name.json and name.jsonc, TUI project tests use tui.json, and migrateTuiConfig creates tui.json. A migrated or directly supplied project tui.json can consequently be ignored. This explains the failure pattern but does not yet prove that correcting discovery will resolve every failing case.

## Evidence

- Initial Host log: .tools/validation/host-suite-first-failures-1788845646016.log
- Isolated targeted log: .tools/validation/host-isolation-targeted-1788846490986.log
- Companion diagnostic summary: docs/HOST_TEST_ISOLATION_DIAGNOSTICS_2026-09-08.json
- Test isolation: runtime/packages/base-harness/test/preload.ts
- Admission fixture: runtime/packages/base-harness/test/kernel-host.test.ts
- Missing extension discovery: runtime/packages/base-harness/src/config/paths.ts
- TUI loader and migration: runtime/packages/base-harness/src/config/tui.ts and tui-migrate.ts

These are developer diagnostics, not independent user validation or Harness Evidence.

## Residual Risk

The initial non-isolated execution may have overwritten or removed existing user configuration. The pre-run contents are unknown; no restoration has been attempted or claimed. User configuration should not be reconstructed from test fixtures or guessed defaults. The exposure was disclosed during this task.

Project TUI JSON discovery remains unfixed in this phase. Correct it with an explicit per-config filename contract and precedence tests, rather than broadening all server configuration formats indiscriminately.

Twenty targeted failures and the unexecuted remainder of the Host suite remain open. The initial five-failure run and later complete targeted run have different coverage and cannot be compared as a regression count.

Real provider accounts, independent usage validation, platform isolation and standalone packaging remain unfinished.
