# ACP Startup CPU Profile

## Situation
The complete Host run still fails the first ACP initialize request under its existing 15-second deadline. Shorter runs and independent CLI initialization succeed. Memory snapshots do not establish a simple free-memory threshold as the cause.

## Reason
Use measured startup samples before selecting another production module for optimization.

## Action
Confirmed CPU-profile flags from the installed Bun 1.3.14 help.
Ran the existing isolated real ACP initialize probe with CPU profiling enabled, preserving the request deadline and making zero model calls.
Summarized the emitted profile. The first summary command had an asynchronous-evaluation syntax error; the corrected analysis invocation succeeded without rerunning the profiled child or changing repository source code.

## Result
The profiled CLI initialized successfully and its child stopped.
Runtime import began at process uptime 678 ms and completed at 3972 ms.
The profile contains 1683 nodes and 788 samples. Summed sample intervals cover 5759 ms.
Approximately 74 percent of the interval weight is associated with frames without a source URL. The largest named source-file share is the Effect internal interpreter, about 10.6 percent. These are sampled interval weights, not precise per-function CPU durations.

## Evidence
The profile and summary are developer diagnostics only, not Harness Evidence or independent user validation.
Unattributed frames and unsymbolized runtime work prevent identifying a particular application function as the cause of the full-run timeout.
A successful profiled short run does not reproduce the cumulative full-run condition, and profiler overhead makes it unsuitable as an uninstrumented performance baseline.
Machine-readable results: ACP_STARTUP_CPU_PROFILE_DIAGNOSTICS_2026-09-09.json.

## Residual Risk
The original ACP timeout remains open. No startup optimization or time-limit change is claimed.
The user was asked whether the first connection must continue including process boot within 15 seconds, or whether startup and ordinary request budgets should be separated. No decision has been applied.
No complete suite, paid model request, repository commit or push was run in this step. Production code and net_monitor.py were unchanged.

