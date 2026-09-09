# TUI Exit Status Limitations

## Situation

The source TUI bootstrap was repaired by preparing the Solid transform before TSX configuration imports. Prior isolated terminal observations showed the home screen, model picker, model change, and plan-only staging without model requests. A separate exit observation returned PTY exit code -1.

## Reason

A diagnostic driver's exit status is not the child's exit status. Static inspection of the installed bun-pty 0.4.8 dependency additionally shows that Terminal.kill() explicitly emits exitCode 0 with a signal after native kill and close. This value is synthetic, not independent evidence of successful application termination.

## Action

Classify the recorded forced/capped termination as inconclusive for normal exit. Keep the observed -1 unresolved rather than converting it to success or diagnosing an application crash. Preserve the source TUI bootstrap fix without changing production process handling on this evidence alone.

## Result

The currently supported usability claims are limited to the observed home, model picker, model selection, and staged plan control. Normal exit, real provider execution, and end-to-end task completion remain unverified. This follow-up made no additional production source changes and ran no additional tests.

## Evidence

- Installed dependency: runtime/packages/core/node_modules/bun-pty/src/terminal.ts, Terminal.kill and Terminal._startReadLoop.
- Core PTY adapter: runtime/packages/core/src/pty/pty.bun.ts, which forwards the dependency's exit events.
- Previous isolated exit observation: childExitCode -1 and modelRequests 0.
- Previous source-bootstrap regression: 1 pass, 0 fail; Host typecheck exit 0. These results are from the preceding fix, not rerun here.
- All observations are diagnostics only, not Harness Evidence or independent user validation.

## Residual Risk

The actual OS process exit status was not independently captured. A follow-up diagnostic should retain the child process handle before shutdown, record the OS status, distinguish requested cancellation and timeout from normal exit, and propagate child failure through the diagnostic driver. Do not mask negative codes or patch the dependency to return zero. No Git operation was performed; net_monitor.py was not changed.

