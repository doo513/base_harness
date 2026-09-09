# Runtime Stabilization Checkpoint - 2026-09-09

## Situation

Implementation is paused at the user's request. This checkpoint preserves the accumulated local runtime, module-boundary, provider, planning, TUI/headless, verifier, test-fixture, and documentation changes since commit 5c479a7. It is an experimental development checkpoint, not a production-readiness declaration.

## Reason

Self-authored tests and scripted diagnostics establish bounded behavior, not independent real-world reliability. Earlier reports contain failed or incomplete observations and remain historical records. The latest successful run must not erase those limitations.

## Action

- Preserve the independent Host, Kernel, KernelHost, Coordinator, Workspace, Security, TUI, and Python verifier boundaries documented in AGENTS.md.
- Preserve restored Host execution/context/lifetime, plan handoff/recovery, provider selection and public-data boundaries, and TUI controls.
- Preserve CLI/ACP lazy startup and response-stream diagnostics, late process-cancellation protection, deferred location loading, and the LSP parent-process-ID correction.
- Prepare the Solid Bun transform explicitly before source TUI and attach configuration imports, avoiding dependence on the launch directory's bunfig preload.
- Finish the already-running isolated exit diagnostic, then stop implementation and prepare the requested Git checkpoint.
- Exclude net_monitor.py and temporary local diagnostic/runtime files from the commit.

## Result

| Area | Supported conclusion | Limit |
| --- | --- | --- |
| Source TUI bootstrap | Missing react/jsx-dev-runtime startup error repaired; focused regression passed | Compiled distribution and real attach UI not established by this check |
| TUI interaction | Home screen, model picker, model change, and plan-only staging observed | Fixture models; no real inference request |
| Normal exit | Explicit /exit returned Windows OS exit code 0 without forced cleanup | One isolated Windows observation, not cross-platform proof |
| PTY reporting | The same normal exit was reported as -1 by bun-pty | Do not interpret the PTY value alone as application failure or success |
| Host regression | Latest full run passed before the final TUI bootstrap patch | Full suite not rerun after that patch |
| Overall readiness | Development checkpoint suitable for continued experimentation | Real OAuth/provider task completion and independent user validation remain open |

## Evidence

- Latest full Host run before the TUI bootstrap change: 3283 pass, 60 skip, 1 todo, 0 fail, 3344 tests across 254 files, 1676.63 seconds.
- TUI bootstrap targeted regression after the change: 1 pass, 0 fail, 3 assertions; Host typecheck exit 0.
- New exit observation retained the Windows child process handle before issuing /exit: OS exit 0, PTY exit -1, diagnostic driver exit 0, forcedCleanup false, modelRequests 0.
- Earlier package results are recorded in their respective reports; they are not represented as rerun at this checkpoint.
- See HOST_BOOTSTRAP_FULL_REGRESSION_PASS_2026-09-09.md, TUI_SOURCE_JSX_BOOTSTRAP_FIX_2026-09-09.md, TUI_EXIT_STATUS_LIMITATIONS_2026-09-09.md, and RUNTIME_STABILIZATION_CHECKPOINT_DIAGNOSTICS_2026-09-09.json.
- The new OS-handle observation narrows the earlier unresolved exit finding. It does not change historical observations or make diagnostic-driver exit codes trustworthy in general.
- These records are diagnostic artifacts only, not Harness Evidence, Ready, or independent user validation.

## Residual Risk

- Real authenticated provider inference and complete multi-step user workflows remain unverified by this checkpoint.
- Attach, narrow layouts, compiled packaging, and cross-platform terminal restoration are not comprehensively validated here.
- Earlier ACP/LSP full-suite timing failures did not recur in the latest full pass, but their causal resolution is not proven.
- Windows symlink permission-dependent skips do not establish isolation support.
- Earlier test-environment isolation work did not recover the original user configuration affected by the prior fixture-isolation incident.
- No additional full suite or paid model call is run for this pause-and-push request.
- Remote develop was fetched and matched local HEAD before preparing the checkpoint. Push success is reported separately after Git confirms it.

