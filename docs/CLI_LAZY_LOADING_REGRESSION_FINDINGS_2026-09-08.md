# CLI Lazy Loading Regression Findings (2026-09-08)

## Situation
A previous patch moved TUI, attach, run and execute entry modules behind a shared lazy yargs adapter. Its application result had been lost in truncated output. Seven current files match the intended patch after CRLF normalization; no source edits were made in this continuation.

## Reason
The preceding startup observations suggested substantial CLI import cost. Lazy loading was intended to retain the existing command builders and handlers, not create another execution or verification path.

## Action
- Recovered the actual patch state.
- Ran the new lazy-command tests and existing startup-trace tests with Bun 1.3.14.
- Ran the Host typecheck.
- Launched real source CLI root/run/execute/attach help commands with isolated fixture configuration, pure mode and a 30-second per-process bound.
- No real model calls, Git operations or net_monitor.py edits were performed.

## Result
**NOT READY FOR PROMOTION.**
- Tests: 11 passed, 1 failed, 23 assertions.
- Host typecheck failed with 8 errors in the new adapter/test code.
- Root --help: exit 0, stdout 0 bytes, stderr 0 bytes. This is an actual output regression, not merely a test assertion issue.
- run --help: exit 0, stderr 3640 bytes, variant/password options present.
- execute --help: exit 0, stderr 3659 bytes, variant/password options present.
- attach --help: exit 0, stderr 1692 bytes, mini/password options present.
- Zero fixture inference requests; all launched command processes terminated.
- Startup comparison and worker repair validation were deferred because correctness gates failed.

## Evidence
The companion JSON records the observed outputs and gate results. This report is engineering diagnostic material, not Harness Evidence, Ready, or independent user validation.
Source locations: runtime/packages/base-harness/src/cli/lazy-command.ts, runtime/packages/base-harness/src/index.ts, runtime/packages/base-harness/test/cli/lazy-command.test.ts.
The default async-builder help callback path fails to deliver output to the current entrypoint renderer. The exact yargs control-flow cause remains to be established; a simple test-expectation change is not an adequate fix.

## Residual Risk
- New defects remain unfixed pending user approval: actual root-help output, adapter typings, and test callback typings.
- Proposed correction: restore awaited root-help rendering while retaining original option builders/handlers; represent installed yargs async behavior explicitly at the adapter boundary.
- Prior capitalization, readiness-timeout and freshness-test failures remain open.
- No speedup, real-model task completion, native TUI stability, or general product reliability is established by these results.


## Follow-up: Confirmed Async Help Ordering
An isolated diagnostic using the installed yargs 18 and the actual lazy adapter produced:
- Synchronous builder: builder -> callback (282 bytes, --mini present) -> parse return -> await return.
- Lazy builder: callback (0 bytes) -> parse return -> await return -> builder -> console output.
- parse returned a non-Promise in both root-help cases; neither command handler ran.

Installed yargs showHelp schedules the asynchronous default builder with then(...) but returns the parser instance immediately. Its parseAsync only wraps parse's returned value and therefore does not await that detached rendering operation. The CLI entrypoint's finally/process.exit can run before help is rendered. This explains the actual blank root-help process observed above.

The correction must explicitly await rendering or provide a synchronously available default builder; changing a test expectation or merely substituting parseAsync is insufficient. Implementation and type corrections remain pending user approval. No application code was changed during this follow-up.
