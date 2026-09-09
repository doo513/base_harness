# Host ACP Runtime Regression and LSP Parent PID

## Situation

The full Host suite was rerun after replacing the ACP command's full AppRuntime bootstrap with a configuration-scoped runner. No source edits were made while that suite was running.

## Reason

Focused ACP tests did not reproduce the historical first-initialize timeout. The full suite was needed to evaluate that same longer-running context. Inspection of a newly observed LSP failure also exposed a separate process identity contract defect.

## Action

- Ran the same full Host test command with startup/resource diagnostics, Bun 1.3.14, model catalogue fetching disabled, and the isolated test environment.
- Kept the ACP request deadline at 15 seconds.
- Recorded the LSP timeout separately from the ACP timeout and did not infer that both had the same cause.
- After the full suite exited, changed LSP initialize.processId from the language server child PID to process.pid, the parent client.
- Extended the existing initialize-capability test to check both PID equality with the parent and inequality with the child. The assertion block now shuts down the client in finally.
- Ran Host type checking and the LSP client test file after that edit.
- Left net_monitor.py unchanged; no Git operation, push, authentication change, or paid model call was performed.

## Result

The full Host run FAILED: 3280 pass, 60 skip, 1 todo, 2 fail, and 1 additional error. It ran 3343 tests across 254 files, with 45 snapshots and 8872 assertions, in 1871.19 seconds.

The failures were:

- LSPClient interop: document mode falls back to push diagnostics. The runner reported 76631.64 ms against its 30000 ms deadline. A later LSPInitializeError reported the internal 45000 ms initialization deadline.
- ACP model-option subprocess: request:initialize timed out after 15 seconds. The child was still alive and had emitted zero stdout lines.

The ACP boundary change therefore did NOT resolve the full-suite timeout. The last recorded ACP stage was cli.input_ready at child uptime 1039 ms. Subsequent configuration, server import, and startup steps are not individually distinguished by those markers, so the log does not locate the delay to one specific module.

After the separate PID correction, Host type checking exited 0 and the LSP client tests passed: 12 pass, 0 fail, 24 assertions, 23.25 seconds. That isolated result does not establish that the full-suite LSP timeout is fixed.

## Evidence

Developer diagnostics only: diagnosticOnly=true, notHarnessEvidence=true, notIndependentUserValidation=true.

- Full run command and numeric records are captured in the accompanying diagnostics JSON.
- Full log: C:\Users\doo33\Downloads\base_harness\.tools\validation\host-acp-runtime-boundary-1788915059798.log.
- Parent PID semantics are defined by Microsoft's [LSP InitializeParams contract](https://raw.githubusercontent.com/microsoft/vscode-languageserver-node/main/protocol/src/common/protocol.ts).
- Full-run shell-resume instrumentation reached completed at 7325 ms; no corresponding failure was reported.
- The production LSP owner already stops the server process when client creation fails. The failing test calls client creation directly, so the paths have different cleanup ownership.

## Residual Risk

No promotion or broad stability claim is justified. The full suite is not green. Parent PID correctness is a separate protocol fix, not an established explanation for either timeout. Windows symlink cases remain explicitly unsupported rather than verified. No full-suite rerun has been performed after the PID correction. Independent real-user TUI, OAuth, and cross-platform behavior remain unproven.
