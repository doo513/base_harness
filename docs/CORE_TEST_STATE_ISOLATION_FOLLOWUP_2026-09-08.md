# Core Test State Isolation Follow-up

## Situation

The Host suite continues in exec session 89513. While observing that run, the Core test preload was found to lack independent Windows LOCALAPPDATA and Linux XDG state paths. It set database/model fixtures and a Git discovery ceiling, but Core Global could still resolve writable configuration and state to real user directories.

## Reason

The previous Host isolation defect must not recur when running Core tests. Passing assertions do not make a test safe if its setup or cleanup can use real user state.

## Action

- Allocate a unique temporary Core test state directory before importing application Global.
- Set LOCALAPPDATA, APPDATA, XDG data/cache/config/state, test home and managed config paths inside that directory.
- Clear inherited explicit and inline Base Harness config/auth overrides in the test process.
- Preserve existing database/model fixtures and Git discovery ceiling.
- Fail before tests load if Global data, cache, config or state resolve outside the scratch root.
- Add a regression test for all four writable Global state paths and Windows environment roots.
- Cleanup checks the resolved parent and prefix before recursive removal. On Windows EBUSY after bounded retries, keep the scratch directory and emit a warning instead of touching any other path.
- No production runtime or verification rule changed. No repository commit/push was performed; net_monitor.py was not modified.

## Result

Core global/Git/model targeted tests passed: 23 tests, 82 assertions, three files, 22.72 seconds. Core typecheck exited 0. No EBUSY retention warning appeared in this targeted output.

The Host suite is still running at the last observation. Observed failures now include Codex OAuth model catalog expectations, plugin configuration installation, provider User-Agent expectations and project worktree/bare repository identity. The full failure inventory and root causes have not yet been established.

## Evidence

- Core target log: .tools/validation/core-test-state-isolation-1788847580766.log
- Host ongoing log: .tools/validation/host-suite-expanded-1788847294624.log
- Companion diagnostic summary: docs/CORE_TEST_STATE_ISOLATION_DIAGNOSTICS_2026-09-08.json
- Changed files: runtime/packages/core/test/preload.ts and runtime/packages/core/test/global.test.ts.
- Continue observing Host session 89513; do not restart it while the handle remains live.

These are developer diagnostics, not Harness Evidence or independent real-user validation.

## Residual Risk

This is test-state path isolation, not process, network or filesystem sandboxing. Global.tmp retains its existing system-temp location and production account-loading behavior is unchanged.

The full Core suite was not rerun after this preload change. The earlier full Core pass must not be represented as a new full pass under this setup.

The ongoing Host suite has failures and is not a release gate pass. Provider/plugin/project issues require source-level analysis after collecting the terminal result.

The earlier non-isolated Host execution's possible impact on user configuration remains unresolved. No original settings are known and no guessed restoration or credential-file modification was performed.
