# Opt-In Host Startup Stage Diagnostics

Date: 2026-09-08
Status: Implemented. Five targeted tests, Host typecheck and two local startup observations passed. Earlier startup timeouts remain unexplained.

## Situation

Phase46 observed two 30-second default-path Host startup failures without stdout, stderr or model requests. A later explicit pure-mode fixture passed. Those observations did not identify whether the delay occurred in module loading, CLI parsing, runtime service construction or server listen.

## Reason

Increasing a readiness timeout or blaming plugins would not establish the cause. Startup needs a bounded, opt-in timeline before the broad CLI import graph is evaluated, with no prompt, argument, credential, arbitrary error message or workspace path in each event.

## Action

Added runtime/packages/base-harness/src/util/startup-trace.ts and trace points in:
- runtime/packages/base-harness/src/source-launcher.ts
- runtime/packages/base-harness/src/index.ts
- runtime/packages/base-harness/src/cli/effect-cmd.ts
- runtime/packages/base-harness/src/cli/cmd/serve.ts

Added runtime/packages/base-harness/test/util/startup-trace.test.ts and runtime/script/verify-host-startup.mjs.

Tracing is disabled unless BASE_HARNESS_TRACE_STARTUP is exactly 1. Each process emits at most 32 records to stderr with a fixed prefix and field set: version, type, stage, sequence, elapsedMs, processUptimeMs, pid and pureRequested. Stage names come from a runtime-checked fixed list; arbitrary labels are ignored. Synchronous sink failures are contained.

pureRequested records whether BASE_HARNESS_PURE is literally 1 at emission; it is not proof of the effective permission model or plugin isolation.

The timeline distinguishes launcher entry, workspace readiness, CLI imports, CLI parsing/options, AppRuntime import, runtime services, server module import and listen. No execution, verification or retry policy was changed.

The comparison diagnostic creates equivalent fresh local fixture configurations, explicitly removes the pure flag for the default case and sets it for the pure case. It uses the same Bun spawn path and 30-second health bound for both, sequentially. Each stream capture retains at most 64 KiB for parsing, continues draining excess output, and does not persist raw stdout/stderr. Only validated fixed-schema startup events and aggregate byte counts are stored.

The first patch application contained an unintended blank context line at the file beginning and failed before edits were applied. Correcting the patch format allowed the same intended changes to apply. This was an application-format issue, not an observed external source change.

## Result

- Five trace unit tests passed with 10 assertions.
- Host typecheck passed.
- Default-mode Host became healthy in 10.15 seconds.
- Pure-mode Host became healthy in 8.38 seconds.
- Both produced 14 startup events, ending at host.listen_ready.
- Neither fixture received a model inference request.
- Captured output stayed below the cap.
- The combined selected gate command exited 0.

Observed timing breakdown, in seconds:

| Interval | Default | Pure |
| --- | ---: | ---: |
| Process uptime at first trace | 1.260 | 0.992 |
| CLI command module graph import | 6.212 | 4.959 |
| AppRuntime module import | 0.928 | 0.697 |
| Runtime service start to Host handler | 0.429 | 0.406 |
| Server module import | 0.763 | 0.728 |
| Listen call | 0.400 | 0.458 |
| Total observed health readiness | 10.150 | 8.380 |

CLI module loading was the largest measured interval in both observations. The current index eagerly imports all command definitions before parsing arguments. This makes selective command loading a concrete candidate for subsequent work, but does not identify an individual package as the cause.

The new diagnostic did not reproduce the previous default-path timeout. It did not fix or invalidate those failures.

## Evidence

- Gate log: .tools/validation/restoration-phase47-startup-tracing-gates.log
- Startup comparison: .tools/validation/restoration-phase47-startup-comparison.result.json
- Companion record: docs/evidence/HOST_STARTUP_STAGE_DIAGNOSTICS_2026-09-08.json
- Previous failures: docs/REPAIR_EXHAUSTION_AND_STARTUP_VARIABILITY_2026-09-08.md

Both controlled Host termination promises were awaited. Their Bun exitCode properties were null following intentional termination; numeric signal-derived exit statuses were not captured and null must not be interpreted as exit 0. The diagnostic supervisor's own exit code was 0.

## Usage

To observe a source Host launch, set BASE_HARNESS_TRACE_STARTUP=1 in that invocation's environment. Use stderr capture rather than mixing diagnostic lines into an interactive TUI display. Remove the flag to restore the default silent behavior.

To repeat the paired local diagnostic from the repository root:

```powershell
$env:BASE_HARNESS_PYTHON = Join-Path $PWD '.tools/verifier/Scripts/python.exe'
$env:BASE_HARNESS_DISABLE_MODELS_FETCH = 'true'
$env:BASE_HARNESS_VALIDATION_TAG = 'host-startup-comparison-local'
& ./.tools/bun-1.3.14/bun.exe run runtime/script/verify-host-startup.mjs
```

Choose a new tag for each run: the result uses exclusive creation to preserve existing diagnostic records. The script controls tracing and pure selection per child process.

## Residual Risk and Next Work

One sequential pair is not a reliability benchmark, a performance regression threshold or a causal plugin experiment. Order, cache state, system load and trace I/O can affect timings. Earlier 30-second failures remain open.

A missing event or the last observed stage only narrows the observation boundary; it does not prove the exact blocking function. Diagnostics before the first launcher event cannot observe all native Bun/process initialization work. Process uptime provides context for that gap.

Diagnostic records are not authenticated Harness Evidence and have no Ready authority. The whitelist prevents this tracer from accepting arbitrary text but does not make another process's stderr trustworthy.

This phase did not rerun the full suite, live TUI, real-provider/OAuth flow or worker repair scenarios. The earlier Python regression gate still has the pending freshness-fixture error; no requested correction has been applied. Phase38 and phase40 issues also remain unchanged.

Next, inspect a shared lazy-command registration approach so serve need not load unrelated command modules, while retaining one CLI option contract and the same Host Coordinator. Avoid a parallel execution path or duplicated verification policy. Further timeout reproduction should use these stage records rather than silently increasing the deadline.

No Git operations, commits or push occurred; net_monitor.py was untouched. This report is an engineering record, not independent user acceptance.
