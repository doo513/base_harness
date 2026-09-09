# Project TUI JSON Discovery Repair

## Situation

The previous isolated Host target run passed 25 tests and failed 20. Failures included project attention settings, keybinds, plugin configuration and migration results not being applied.

ConfigPaths.files searched only name.jsonc. The TUI supports tui.json as well as tui.jsonc, and migration writes tui.json. Global and explicit config paths could work while project JSON settings were ignored.

## Reason

Make project discovery match the existing TUI file contract without broadening the server's project configuration contract. Keep nearest-directory precedence and deterministic JSONC-over-JSON precedence at the same location.

## Action

- ConfigPaths.files now searches tui.jsonc and tui.json only when discovering TUI files.
- Other names, including base-harness, remain JSONC-only for project discovery.
- The underlying walk visits nearest directories first and collects JSONC before JSON; reversing results applies ancestor files first and JSONC last within each directory.
- Added tests for same-directory JSONC precedence, nearer JSON overriding ancestor JSONC, and server project JSONC-only discovery.
- Retained the prior Windows scratch-state isolation and execution-admission guards.
- No verifier, model reasoning identifier, evidence policy or Ready authority was changed.
- No Git operation was performed; net_monitor.py was not modified.

## Result

The targeted run passed all 48 tests across four files, with 162 assertions in 29.63 seconds. Host typecheck exited 0. All 20 previously failing tests in this targeted set now pass.

These are actual config service and filesystem tests, not independent user testing. The test sources cover the TUI loader, KernelHost execution handoff, CLI errors and Windows test-state paths.

A broader Host suite has been started with a 30-second per-test timeout and a five-failure stop. It remains running at the last observation; no full-suite success is claimed. Its logs have passed the previously failing configuration section and show global configuration under process-owned scratch state.

## Evidence

- Target log: .tools/validation/tui-json-discovery-1788846709927.log
- Broader Host log: .tools/validation/host-suite-after-tui-json-1788846781735.log
- Broader Host exec session: 22159; poll this existing handle rather than starting another run while it remains live.
- Companion summary: docs/TUI_PROJECT_JSON_DISCOVERY_DIAGNOSTICS_2026-09-08.json
- Implementation: runtime/packages/base-harness/src/config/paths.ts
- Regression coverage: runtime/packages/base-harness/test/config/tui.test.ts

The companion summary is diagnostic-only and is not Harness Evidence or independent user validation.

## Residual Risk

The prior non-isolated test execution may have changed or removed user settings. A metadata-only check found no base-harness.jsonc, tui.json, tui.jsonc or base-harness.jsonc.tui-migration.bak in the actual user LOCALAPPDATA/base-harness directory. Pre-run contents are unknown; this does not establish whether those files existed before the tests. No credential content was read and no restoration was attempted.

No claim is made that no backup exists elsewhere. Unknown original settings must not be replaced with guessed defaults or test fixture contents.

Full Host suite completion, real OAuth/provider accounts, genuine LLM task quality, native TUI visual coverage, platform isolation and standalone packaging remain open.
