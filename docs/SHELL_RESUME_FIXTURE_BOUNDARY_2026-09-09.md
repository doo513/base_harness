# Shell Resume Fixture Boundary Diagnostics

## Situation
The latest complete Host suite ended with two failures: ACP initialize and shell-to-loop resume timeouts. The shell timeout also reproduced twice in a two-test isolated run. Test-body finalizer diagnostics did not reveal a phase before termination.

## Reason
The test runner builds service layers, creates a temporary Git repository and loads instance context before calling the test body. All of these stages share the existing 10-second timeout. Observing only the body's finalizer cannot distinguish these boundaries.

## Action
Added an opt-in test-only phase tracer controlled by BASE_HARNESS_TRACE_TEST_PHASES=1. It writes at most 128 small stderr records and does not record paths, commands or credentials. Instrumented isolated/shared runner entry and layer readiness, temporary-directory setup and cleanup, Git child start/exit, and instance body entry.
No timeout, assertion, production runtime, verification policy or Ready behavior was changed.
Ran the two related tests once with fixture tracing and once with fixture plus existing startup tracing. The latter run also passed Host typecheck.

## Result
Both diagnostic runs passed both tests with 11 assertions: 21.64 seconds and 20.02 seconds for the respective processes.
In the first run, the failing-on-earlier-runs test entered its body 1500 ms after runner entry and released its runner after 8910 ms total.
In the second run, those durations were 1501 ms and 8722 ms. Provider initialization in that run took 910 ms.
These observations rule out a setup hang in these passing samples only. They do not establish the phase responsible for earlier failures.

## Evidence
All phase records are developer diagnostics, not Harness Evidence or independent user validation.
The diagnostic runs demonstrate successful cleanup and provider readiness in the sampled executions. They are not controlled benchmarks and do not prove prolonged stability.
The previous complete-suite result remains 3274 passes, 60 skips, 1 todo and 2 failures.
Machine-readable results: SHELL_RESUME_FIXTURE_BOUNDARY_DIAGNOSTICS_2026-09-09.json.

## Residual Risk
The first selected test has limited headroom under its existing 10-second limit. Exact attribution within its body remains unknown, and diagnostic I/O can alter scheduling.
A later passing sample does not erase the preceding isolated and full-suite failures. Neither failure is marked resolved.
No complete suite was restarted. No paid model request, repository commit, push or net_monitor.py change was made.
A follow-up should capture body stages directly when diagnostics are enabled and inspect timeout cancellation ownership, rather than assuming that initialization or shell ordering is solely responsible.

## Follow-up: Direct Body Phases
Added opt-in direct stderr emission for the existing body phase markers, so observation no longer depends solely on the body finalizer. No deadline or execution behavior changed.
The two selected tests passed again (11 assertions, 20.32 seconds). In the first test, configuration was ready at body +4 ms, the shell was forked at +21 ms, busy state was observed at +57 ms, and no early model call was confirmed at +121 ms. Shell completion was observed at +3295 ms and loop completion at +7184 ms. Overall runner time was 8996 ms.
This sample splits the body delay into 3274 ms from shell fork to completion and 3889 ms from shell completion to loop completion. Those intervals contain more than raw process startup or model execution; their inner causes are not established. Ordering and result assertions passed in this sample, but preceding timeout failures remain unresolved.
