# Host Full Regression Pass With Bootstrap Diagnostics

## Situation

Previous full Host runs failed on the first ACP initialize request, and one also failed during fake LSP server initialization. Focused ACP and LSP runs passed. A selected session workload followed by ACP also passed.

## Reason

The newly added ACP stage markers required a full-run comparison without relaxing timeouts. A passing run must be recorded separately from proof that the historical intermittent failure was fixed.

## Action

- Inspected environment mutation and restoration in selected configuration, provider, and plugin tests. No specific leaked variable explaining ACP startup was established.
- Ran the complete Host suite using Bun 1.3.14, the existing 15-second ACP request deadline, the same test-phase diagnostics, and isolated test configuration.
- Left the source unchanged throughout this run.
- Did not modify net_monitor.py, invoke paid model APIs, change authentication, or run Git operations.

## Result

The full runner exited 0:

| Measurement | Result |
| --- | ---: |
| Passing | 3283 |
| Skipped | 60 |
| Todo | 1 |
| Failing | 0 |
| Additional errors | 0 |
| Total tests | 3344 |
| Files | 254 |
| Snapshots | 45 |
| Assertions | 8889 |
| Duration, seconds | 1676.63 |

The previous ACP and LSP initialization failures did not reproduce in this run. This is one full regression pass, not proof of a causal fix or deterministic real-world reliability. The shell-resume diagnostic reached its completed stage at 6731 ms.

## Evidence

Developer diagnostics only: diagnosticOnly=true, notHarnessEvidence=true, notIndependentUserValidation=true.

- Full command and terminal result are recorded in the accompanying diagnostics JSON.
- Runner log: C:\Users\doo33\Downloads\base_harness\.tools\validation\host-acp-bootstrap-stages-1788917737312.log.
- The preceding failed full run recorded 3280 pass, 2 fail, and 1 additional error. The current suite also contains the new ACP boundary projection test and the LSP parent-PID assertions.
- This run reported Windows symlink operations as unsupported rather than validated.

## Residual Risk

Do not close the historical intermittent startup issue as causally resolved on this result alone. Changed scheduling, caches, memory conditions, or other external state could affect reproduction; none was proven to explain the difference. Skips and todo items remain outside verified coverage. This is not independent user acceptance testing, OAuth verification, a cross-platform certification, a release approval, or a Ready artifact. No commit or push was performed.
