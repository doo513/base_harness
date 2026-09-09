# ACP early EOF and Core full regression

## Situation

Bounded diagnostics showed an EOF-only ACP invocation entering AppRuntime and provider initialization before exceeding its existing five-second shutdown limit. Core's full regression also remained pending after test-state isolation changes.

## Reason

The common effect command wrapper initializes AppRuntime before invoking the ACP handler. Checking EOF inside that handler is therefore too late to avoid initialization. Empty input can return earlier, but checking it must not consume, discard, or eagerly drain buffered protocol bytes.

## Action

- Added an ACP-specific input gate outside the effect command wrapper. The shared wrapper and other commands are unchanged.
- Used paused-stream readability and read(0) to distinguish available data from empty EOF without consuming input.
- Propagated stream errors and premature close rather than treating them as clean EOF; removed gate listeners after settlement.
- Added typed input-wait, input-ready, and input-EOF startup trace stages.
- Strengthened the existing real ACP subprocess EOF test to require an EOF trace and absence of runtime-import and runtime-service-start traces, while retaining its five-second deadline.
- Added seven input-gate cases covering empty EOF, open idle input, buffered and delayed input, data followed by EOF, stream errors, and premature close.
- Ran the targeted Config, Truncate, diagnostic, and ACP group and Host typecheck.
- Inspected Core's configured test preload and ran its complete suite and typecheck after the existing test-state isolation changes.
- Did not perform Git operations, touch net_monitor.py, change OS permissions, or increase timeouts.

## Result

| Check | Result |
| --- | --- |
| Targeted Host group | 138 passed, 0 failed, 366 assertions, 7 files, 117.06 seconds |
| Host typecheck | Exit 0 |
| Full Core regression | 1110 passed, 7 skipped, 0 failed, 3063 assertions, 146 files, 244.92 seconds |
| Core typecheck | Exit 0 |

The targeted group now passes the previously failing ACP EOF case. Core's post-isolation full regression is complete. These results do not replace the pending complete Host rerun.

## Evidence

Developer diagnostics only; not Harness Evidence, Ready artifacts, or independent user validation.

- Runtime: bundled Bun 1.3.14 on Windows.
- Targeted validation session 20586 and Core session 42739 terminated with exit code 0.
- The real ACP test closes stdin immediately and verifies completion within the existing five-second operation deadline without AppRuntime initialization.
- Input-gate unit tests compare the exact bytes after the gate, including delayed multibyte input and buffered input followed by EOF.
- Existing ACP model selection, lifecycle, and prompt-content subprocess cases remain in the passing targeted group.
- Core preload routes Windows LOCALAPPDATA/APPDATA and XDG paths into a unique temporary state directory and rejects Global paths outside it before tests run.
- Core executed all 1117 reported tests across 146 files without early bail or snapshot update mode.

## Residual Risk

- Full Host regression must still demonstrate whether Truncate loading and ACP first-request timing remain reliable under the complete suite.
- CLI module loading still precedes the ACP-specific gate. This change avoids unnecessary service initialization, not all startup work.
- The buffered-input gate preserves transport bytes; it does not redefine ACP behavior for in-flight requests when a peer closes its connection.
- Seven Core skips and unavailable Windows native symlink cases are not validated behavior.
- Real OAuth/provider connections, long-running TUI behavior, independent user acceptance, and broader deployment stability remain unproven.
