# TUI Source JSX Bootstrap Fix

## Situation

The first direct TUI attempts returned execution-tool serialization errors. Redirecting output produced usable diagnostic records and exposed the actual child failure: react/jsx-dev-runtime could not be resolved from the TUI configuration TSX module.

## Reason

The TUI uses Solid and @opentui/solid, not React. Its package bunfig.toml registers @opentui/solid/preload, but an absolute source-entry launch from an unrelated workspace cannot rely on that cwd-specific configuration being loaded. Installing React would not establish the required Solid transformation.

## Action

- Added cli/tui/prepare-runtime.ts using the existing, idempotent ensureSolidTransformPlugin API.
- Called it before TuiConfig imports in both the TUI and attach command handlers.
- Kept preparation after the mini-mode branches, leaving mini/headless execution unchanged.
- Added a fresh subprocess regression test with an unrelated temporary cwd and no package bunfig preload. It prepares the plugin twice and loads the real TUI TSX configuration.
- Ran actual TUI processes through the repository's existing bun-pty adapter, with output redirected to diagnostic logs.
- Used isolated temporary homes and loopback-only model fixtures that reject inference requests.
- Did not modify user authentication, user configuration, or net_monitor.py.

## Result

Host type checking passed. The source-bootstrap regression passed: 1 test, 3 assertions, 12.85 seconds.

Actual terminal observations after the fix:

| Behavior | Observation |
| --- | --- |
| Startup | Base Harness home prompt displayed |
| Slash menu | Command suggestions displayed |
| Model picker | Select model dialog displayed both diagnostic models |
| Model change | Home prompt changed from Diagnostic Model A to Diagnostic Model B |
| Plan control | /plan produced next: plan-only / 1 staged |
| Model requests | 0 |
| Exit command | Process ended after explicit /exit selection; PTY reported childExitCode=-1 |

The first interactive run lost its control connection around its bounded lifetime, so it is not evidence of a successful explicit exit. A separate short exit run accepted the exit selection and ended, but its negative PTY exit status is unresolved. Driver process exit code 0 must not be substituted for the child exit status.

## Evidence

Developer diagnostics only: diagnosticOnly=true, notHarnessEvidence=true, notIndependentUserValidation=true.

- Before-fix log: C:\Users\doo33\Downloads\base_harness\.tools\validation\tui-pty-redirect-1788919926937.log.
- Post-fix interactive log: C:\Users\doo33\Downloads\base_harness\.tools\validation\tui-after-jsx-1788920168551.log.
- Separate exit log: C:\Users\doo33\Downloads\base_harness\.tools\validation\tui-clean-exit-1788920401493.log.
- The accompanying JSON contains the observed terminal text and child status, without live control tokens.
- No new dependency was installed. The existing OpenTUI Solid plugin was reused.

## Residual Risk

These are agent-operated native PTY observations, not independent end-user acceptance or pixel-level Windows Terminal validation. Real OAuth, paid/remote model execution, full PlanSpec execution, attach interaction, narrow-terminal layout, and terminal restoration remain unverified here. The negative PTY exit code requires separate investigation. The previously passing full Host suite preceded this fix; only Host type checking and the focused regression were rerun afterward. No commit or push was performed.

## Relation to the Previous Unverified Report

TUI_INTERACTIVE_VALIDATION_UNVERIFIED_2026-09-09.md records the earlier tool-limited attempts. Output redirection subsequently recovered a working observation channel, which is why the later checks above have concrete UI observations. That does not retroactively make the earlier attempts successful.
