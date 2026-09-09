# ACP Differential Startup Investigation

## Situation
ACP initialize still exceeded its existing 15-second deadline in the latest complete Host run, while isolated ACP regressions passed. That full run remains failed.

## Reason
Before changing more production code, distinguish eager dependency loading, test-file discovery effects and effects of executing LLM tests before ACP.

## Action
Inspected the Host bundled Provider loader, Core AISDK imports and Npm implementation. Bundled Provider modules and Arborist already use dynamic imports, so those implementations were not changed.
Ran only the previously failing ACP case while discovering all 253 Host test files.
Ran session LLM tests followed by ACP config-option tests.
Added optional numeric memory snapshots to test-only ACP diagnostics at spawn and observation. Sampling failures or invalid counters are omitted, and extra fields are not projected.

## Result
- All-file discovery with one selected ACP case: 1 passed, 0 failed, 3336 filtered out, 8 assertions, 19.66 seconds.
- LLM plus ACP config-option tests: 34 passed, 0 failed, 114 assertions, 41.34 seconds.
- Resource diagnostic and ACP config-option tests: 11 passed, 0 failed, 54 assertions, 31.19 seconds.
- Host typecheck after changes: exit 0.

## Evidence
These are developer diagnostics, not Harness Evidence or independent user acceptance.
The selected ACP operation did not reproduce the full-run timeout under either shorter setup. These passing samples do not rule out cumulative resource pressure, other test side effects or timing variation.
Future ACP timeout messages can include parent RSS, parent heap use and free/total system memory at process launch and observation. No command, environment value, credential or raw provider payload is added by this sampling.
Machine-readable results: ACP_DIFFERENTIAL_STARTUP_DIAGNOSTICS_2026-09-09.json.

## Residual Risk
No memory-pressure cause has yet been measured at a failing ACP launch. No startup performance improvement or full-suite fix is claimed.
The latest complete Host result remains 3274 passes, 60 skips, 1 todo and 2 failures. Three resource-diagnostic tests were added afterward; the full suite was not rerun.
No timeout was increased and no failure was converted into a skip.
Actual OAuth/provider use and independent practical stability remain unverified.
No repository commit, push, user credential change or net_monitor.py change was made.

