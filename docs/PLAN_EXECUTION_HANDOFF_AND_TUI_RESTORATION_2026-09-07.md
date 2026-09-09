# Plan execution handoff and TUI restoration

Date: 2026-09-07

Status: the actual TUI plan/execute path is restored in the local fixture. Overall restoration remains incomplete because the manual verification API omits Kernel status fields.

## Situation

The preceding restoration corrected the TUI planning label, the model-selection test's branded identifiers, synthetic root integration messages, and separate planning/execution run identities. Its real TUI test then exposed a regression:

`OrchestrationError: WorkGraph is not accepted during direct`

A new execution run had an accepted contract, but its Workspace orchestration phase was still `direct`. No worker was dispatched, neither result file was created, and Ready remained unavailable. The previous 100 passing tests did not detect this because the handoff test stopped after creating the new run.

The preceding attempt was interrupted before its implementation report was written. This document records that failed intermediate state as well as the corrective work; it does not relabel the earlier failure as a success.

## Reason

Kernel planning state and Coordinator/Workspace execution phase are separate contracts. Setting Kernel state to `executing` cannot by itself authorize a WorkGraph in a newly created Workspace run.

The Coordinator must put an accepted execution run into `planning` before dispatch. A Host dispatch exception must also become a typed execution failure, not an `awaiting_input` state with no actual user decision to resolve.

## Action

1. Updated Coordinator `beginPlanExecution()` to enter and persist `planning` after the new verifier accepts the unchanged reviewed contract.
2. Preserved the fresh run ID, planning-run lineage, GoalContract hash, configured profile, and independent verifier lifecycle.
3. Added `reportPlanExecutionFailure()` using the existing trusted failure and root completion-latch path.
4. Routed Kernel handoff exceptions to that Host failure path instead of presenting them as a user ambiguity.
5. Extended the real-Python handoff regression through WorkGraph dispatch, Overlay editing, candidate verification, commit, integration, and root Ready.
6. Added a negative dispatch case proving that an internal failure is blocked and cannot be turned into Ready by manual re-verification.
7. Added `runtime/script/verify-plan-execute-host-flow.ts` to exercise the actual Host control API, including plan-only, manual verification, execute, model/effort preservation, synthetic integration context, and real evidence.
8. Extended the local fixture's explicit model catalog to support the automated reasoner case and corrected its plan-only response so it no longer claims files have already been written.

No model or reasoning-effort names were added to production Kernel policy. The fixture advertises `max`; the transport test checks that this exact provider-native value survives the Host boundaries.

No commit or push was performed. `net_monitor.py` was not changed.

## Result

### Actual TUI: passed

The TUI was launched against a fresh local Host. The provider connection dialog, model selector, and reasoning selector were used to select `fixture-reasoner` and `max`.

- `/plan` produced `PLAN_READY`, zero workers, zero verified evidence, and neither requested result file.
- The overlay explicitly instructed the user to use `/execute` and stated that Ready had not been issued.
- `/execute` opened a different run and dispatched both WorkUnits.
- Both workers completed, both files exactly contained `fixture success\n`, and the real Python verifier produced a Ready attestation covering both required claims and criteria.
- The TUI displayed `VERIFIED STATE READY (adaptive)` with two completed workers and four evidence references.
- Contract review and plan review each occurred once. Execute did not repeat them.
- All eleven non-title pipeline model requests retained `fixture-reasoner` and `max`. The auxiliary title request used the configured small model.
- Root integration context was persisted with `synthetic: true` and no longer rendered as a new user request.
- The TUI exited with code 0. The tracked fixture/server launcher exited with code 0 after its stop request.

Planning run: `run-a81339a2-335c-4755-a910-57706117f661`

Execution run: `run-7285ddf2-59bf-4fb9-ac4f-11db7cea80db`

Plan: `34841003-6546-484d-a340-cf1a2f9a1995@1`

Root session: `ses_f84a866b5ffefhT0Qiv8a5iei0`

### Typechecks and regression tests

| Check | Result |
| --- | --- |
| Coordinator typecheck | Passed |
| KernelHost typecheck | Passed |
| Host typecheck | Passed |
| TUI typecheck | Passed |
| Coordinator tests | 40 passed |
| KernelHost tests | 29 passed |
| TUI status-presentation tests | 14 passed |
| Host boundary tests, first run | 19 named tests passed; one unnamed cleanup hook timed out |
| Host boundary tests, bounded retry | 19 passed, zero failures; 4.789 seconds with model-catalog fetching disabled |

The 102 named regression tests passed across these runs. The initial cleanup timeout is retained as a residual reliability issue; the successful retry does not prove its cause.

### New Host API fixture: correctly remains red

The automated Host API fixture failed at its plan-only manual-verification assertion:

`POST /session/:sessionID/harness/verify` returned no `planningState`, while `GET /session/:sessionID/harness` had returned `planningState: "plan_ready"`.

This is a response-contract discrepancy, not evidence that the plan executed or that Ready was issued. The fixture stops before its execute step. Its assertion was not removed or weakened to manufacture a passing result.

The successful interactive TUI run above exercised execute separately and proves the corrected handoff works. It does not resolve the manual-verification API discrepancy.

## Evidence

- `.tools/validation/restoration-phase18-gates.json`: four typecheck results, regression output, and the initial Host cleanup timeout.
- `.tools/validation/restoration-phase18-host-boundary-retry.json`: bounded Host retry, environment difference, and successful result.
- `.tools/validation/real-host-plan-execute.result.json`: reproducible API contract failure before execute.
- `.tools/validation/restoration-phase18-tui-plan-ready.json`: plan-only status and both missing result files.
- `.tools/validation/restoration-phase18-tui-execute.json`: fresh execution identity, exact file contents, persisted manifests, request metadata, synthetic integration part, and real Ready evidence.
- `.tools/validation/restoration-phase18-tui-audit.json`: selected PTY output and tracked process exits.
- `.tools/validation/restoration-phase17-tui-execute.json`: earlier failed handoff, with no worker dispatch, no result files, and no Ready.

The successful TUI fixture workspace is `C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-X8IR2N\workspace`.

The independently checked Ready artifact is:

`C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-X8IR2N\state\base-harness\runs\a18949e44c4a319b-cf34a7ce\artifacts\46\46647da7c6c2a6fa524314cd4a318dbf45124f3e4fa085d34c62eab068bb702f.json`

## Residual Risk and next work

1. Normalize the public verify response through the same Kernel-enriched Host snapshot used by GET/control/events; also check cancel and other status-returning endpoints for the same omission.
2. Keep the new API fixture's `planningState` assertion, then pass its positive and injected-integration-failure runs.
3. Investigate the initial Host cleanup-hook timeout. Disabling catalog fetching correlated with a successful retry, but causation is not established.
4. The local fixture proves execution wiring, native option preservation, MCP use, and verifier gating. It does not certify live OAuth/provider compatibility, real-model reasoning quality, or arbitrary complex-project performance.
5. The PTY checks cover the observed narrow-terminal controls and status display, not comprehensive CJK wrapping, Linux terminal behavior, or OS sandbox/process-tree isolation.

Overall completion and release promotion are not claimed.
