# ACP Bootstrap Boundary Diagnostics

## Situation

The full Host suite still times out on the first ACP initialize request. After the command runtime split, the last recorded startup event was cli.input_ready, which did not distinguish several subsequent initialization stages.

## Reason

Further optimization without identifying the delayed stage would be speculative. The diagnostic must separate module loading from configuration I/O and server acquisition without changing timeouts, protocol responses, or readiness policy.

## Action

- Added declared ACP startup stages for Config import, command runtime imports, command service acquisition, Host server import, ACP agent import, global configuration reading, server listening, and connection creation.
- Retained the existing opt-in BASE_HARNESS_TRACE_STARTUP flag, 32-event bound, synchronous failure-tolerant sink, and numeric timing projection.
- Added a test proving all ACP boundary stages survive diagnostic projection while arbitrary credential fields do not.
- Ran Host type checking, the diagnostic test file, and one actual CLI initialize probe with an isolated temporary home and loopback provider fixture.
- Left source execution order, 15-second request deadline, verifier policy, and net_monitor.py unchanged.

## Result

Host type checking passed. Diagnostic tests passed: 8 pass, 0 fail, 22 assertions, 1.129 seconds.

The single local probe initialized successfully, made zero model calls, and stopped its child process. Observed intervals in milliseconds:

| Stage | Duration |
| --- | ---: |
| Config module import | 799 |
| Command runtime imports | 6 |
| Command service acquisition | 112 |
| Host server module import | 2196 |
| ACP agent module import | 52 |
| Global configuration read | 13 |
| Server listen | 533 |

The connection-ready marker occurred at child process uptime 4307 ms. It is not an end-to-end task completion measurement.

## Evidence

Developer diagnostics only: diagnosticOnly=true, notHarnessEvidence=true, notIndependentUserValidation=true.

- Bun 1.3.14.
- bun run typecheck: exit 0.
- bun test --timeout 30000 --only-failures test/cli/acp-diagnostics.test.ts: exit 0.
- Actual child command: bun run --conditions=browser src/index.ts acp with loopback network options and a temporary home.
- Numeric resources, stage records, and interval calculations are included in the accompanying diagnostics JSON.
- Raw probe log: C:\Users\doo33\Downloads\base_harness\.tools\validation\acp-bootstrap-stages-1788917199008.log.

## Follow-up: Session Workload Before ACP

A narrower reproduction run executed test/session followed by test/cli/acp/config-options.test.ts under the same 15-second ACP request deadline. It completed with 404 pass, 20 skip, 1 todo, 0 fail, and 1125 assertions across 425 tests in 19 files (218.13 seconds).

The ACP timeout did not reproduce in this selected session workload. This rules out neither session interactions in the full suite nor system load; it only shows that this session-only sequence was insufficient on this run. No source was changed for this experiment. The existing full-suite failure remains unresolved.

## Residual Risk

This is diagnostic instrumentation, not a fix for the long-suite startup timeout. A single successful local initialization cannot identify the cause of the failed full-suite initialization. Its parent process, memory conditions, and workload differ from the full test runner. No comparative speedup, independent real-user stability, OAuth validation, or completion-gate assurance is claimed. No full-suite rerun or Git push was performed in this step.
