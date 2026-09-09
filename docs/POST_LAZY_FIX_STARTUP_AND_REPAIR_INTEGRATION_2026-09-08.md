# Post-Lazy-Fix Startup and Repair Integration (2026-09-08)

## Situation
Lazy CLI help and type errors were repaired. Targeted tests and Host typecheck passed in the previous turn. Deferred startup and local repair integration checks were resumed.

## Reason
Passing adapter unit tests does not establish that the actual Host, provider metadata, worker sessions and verifier still cooperate correctly. Startup latency also requires measurement rather than inference from imports.

## Action
- Ran the existing bounded startup diagnostic for fresh default and pure-mode fixture environments.
- Ran the existing two-worker local repair fixture in explicit pure mode.
- Used local deterministic Provider HTTP responses and local MCP; no real paid model or OAuth session.
- Read the generated diagnostic result files once. No application source was edited.

## Result
Both diagnostics passed; the combined supervisor exited 0.

| Observation | Result |
| --- | --- |
| Default Host health | 14.950 s |
| Pure Host health | 8.166 s |
| Default CLI import / runtime import | 5.641 s / 5.449 s |
| Pure CLI import / runtime import | 4.866 s / 0.656 s |
| Repair-run Host health | 8.827 s |
| First provider metadata response | 10.545 s additional |
| Repair client duration | 34.105 s |
| Failed worker | Same child session, one repair, two writes |
| Independent worker | One write, no repair |
| Root result | ready; client exit 0; zero active/queued workers |

The initial failed worker candidate was absent from the base workspace before repair. Original model and exact high variant were retained. Public provider metadata omitted credentials/private options. Worker catalogs excluded forbidden tools. Selected current Ready families were active while historical dispute information remained preserved.

## Evidence
Run: run-da0be9cd-e3db-4ff9-bb9e-dc5630066b51
Session: ses_f8112761effeDQFAJQaNk33cYT
Companion JSON includes stage durations, checked invariants and result references.
The startup diagnostic intentionally terminated both servers after health; its recorded exitCode remains null despite awaiting process termination. The repair Host was intentionally terminated after the client completed (143); the client and supervisor exited 0.

## Residual Risk
- The earlier pair measured approximately 10.150 s default and 8.380 s pure. The new pair does not demonstrate an overall startup improvement. Sampling order, cache and host workload were not controlled.
- A healthy endpoint is not equivalent to a usable model-selection interface: initial provider enumeration added about 10.5 seconds.
- Terminal phase/outcome were ready while planningState was still executing. This is an observed presentation-state inconsistency requiring follow-up.
- Root/metrics repair counts were zero while one child had repairCount=1. These may intentionally be scope-specific; verify aggregation semantics before calling them incorrect.
- Scripted repair is not evidence that a real model can independently diagnose and repair failures.
- Earlier startup timeouts and unrelated pending test failures remain open. No full-suite, native TUI or independent user stability conclusion is claimed.
- Git and net_monitor.py were untouched.
