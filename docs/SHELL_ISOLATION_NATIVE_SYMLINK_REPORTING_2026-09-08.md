# Shell isolation diagnostics and native symlink reporting

## Situation

The previous full Host regression reported shell permission timeouts and five native symlink failures in filesystem, glob, and Zed editor-context tests. Passing isolated tests is not evidence that full-suite or real-user reliability has been established.

## Reason

A shell timeout must be reproduced before changing runtime behavior or increasing timeouts. Native symlink creation failures caused by the Windows environment must be reported as unsupported checks, not silently counted as successful validation.

## Action

- Re-ran the shell permission cases and then the complete shell test file without changing runtime code or test timeouts.
- Updated filesystem, glob, and Zed editor-context tests to use the existing native symlink capability probe.
- Restricted conditional skips to cases requiring unavailable native file or directory symlink capabilities.
- Added explicit symlink types and lstat assertions to capability-dependent cases.
- Kept the mandatory BASE_HARNESS_REQUIRE_SYMLINK_TESTS=1 gate fail-closed.
- Added a separate Zed database-path error case using a regular file as an intermediate path component. This does not replace native symlink coverage.
- Did not change OS permissions, production shell behavior, credentials, or net_monitor.py. No Git operations were performed.

## Result

| Check | Result |
| --- | --- |
| Isolated shell permission cases | 4 passed, 87 filtered, 20 assertions, 11.75 seconds |
| Complete shell test file | 91 passed, 0 failed, 259 assertions, 84.00 seconds |
| Filesystem, glob, and Zed tests | 90 passed, 5 skipped, 0 failed, 105 assertions, 7.67 seconds |
| Mandatory native symlink gate | Exit 1; 0 passed, 3 failed, 3 module errors; SYMLINK_CAPABILITY_REQUIRED |
| Host typecheck | Exit 0 |

Windows file and directory symlink probes returned EPERM. The five skipped cases remain unvalidated. The mandatory gate correctly refused validation on this host; that refusal is not native capability validation.

## Evidence

These are developer diagnostics only, not Harness Evidence, Ready artifacts, or independent user validation.

- Runtime: bundled Bun 1.3.14 on Windows.
- Shell checks used test/tool/shell.test.ts with the existing 30000 ms test timeout.
- Native checks used test/util/filesystem.test.ts, test/util/glob.test.ts, and test/cli/tui/editor-context-zed.test.ts.
- Normal native reporting used BASE_HARNESS_REQUIRE_SYMLINK_TESTS=0; the mandatory gate used value 1.
- Host typecheck used bun run typecheck.
- All observed validation processes terminated without watchdog timeout.
- Machine-readable results: SHELL_ISOLATION_NATIVE_SYMLINK_DIAGNOSTICS_2026-09-08.json.

## Residual Risk

- The original full-suite shell timeout did not reproduce in isolation. Its root cause and behavior under full-suite load remain unresolved.
- Full Host regression must be rerun after the accumulated changes; targeted passes do not supersede the previous failed full run.
- Full Core regression after test-environment isolation remains pending.
- A capable Windows runner is required to validate Windows native symlink behavior. Linux results alone cannot establish Windows behavior.
- Mandatory native capability enforcement is not claimed to be wired into every CI entry point.
- Real TUI use, OAuth connections, long-running stability, and independent user acceptance remain unproven.
