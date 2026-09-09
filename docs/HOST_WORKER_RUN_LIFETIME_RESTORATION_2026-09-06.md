# Host Worker Run Lifetime Restoration

Date: 2026-09-06
Status: PARTIAL. Worker lifetime restored; overall execution must not be promoted.
Repository: C:/Users/doo33/Downloads/base_harness

## Situation

Phase 14 restored request-scoped InstanceRef capture, both independent meta reviews, and read-only MCP access. Real planned runs then failed before worker model calls with "Task cancelled".

This phase fixes that cancellation defect and tests the real TUI as well as the headless fixture. The expanded check found two additional failures that invalidate any claim of complete TUI/headless execution parity.

## Reason

- session/llm.ts owns an AbortController inside a scoped stream and calls abort on normal stream release as well as interruption.
- TaskTool copied the parent tool context into detached Coordinator worker execution, including that stream's AbortSignal.
- A foreground Task listener reacts to that signal by cancelling the child session and its background job.
- Detached WorkUnits must instead live until the Coordinator run cancels or the workspace closes.
- A passing artifact check is insufficient if required Host integration fails or a later verification request clears that failure.

## Action

- Added a Coordinator-owned execution AbortController per run.
- Added an explicit run signal to WorkerExecutionRequest and IntegrationExecutionRequest.
- Run cancellation, workspace disposal, and test reset abort that run signal.
- Managed worker contexts now replace the parent stream signal with the Coordinator signal.
- Added runUntilCancelled to bind pending Effect work to the run and execute child/root cleanup on interruption.
- Registered the actual child session for cancellation cleanup, including interruption before Task's ordinary foreground wait starts.
- Handled an already-aborted signal when installing the Task foreground listener.
- Added Coordinator and Host lifetime regression tests.
- Did not change Python promotion rules, candidate attestation, Overlay commit policy, model reasoning names, or provider implementations.
- Did not run git, commit, push, or touch net_monitor.py.

Changed source and tests:

- runtime/packages/coordinator/src/index.ts
- runtime/packages/coordinator/src/contracts.ts
- runtime/packages/base-harness/src/tool/task.ts
- runtime/packages/base-harness/src/harness/execution-lifetime.ts
- runtime/packages/coordinator/test/execution-lifetime.test.ts
- runtime/packages/base-harness/test/harness/execution-lifetime.test.ts

## Result

| Check | Observed result | Scope of the evidence |
| --- | --- | --- |
| Coordinator typecheck | PASS | tsc --noEmit, Bun 1.3.14 |
| Host typecheck | PASS | tsgo --noEmit, Bun 1.3.14 |
| Coordinator tests | 35 passed, 0 failed | Includes real Python candidate integrity and parallel/local-repair tests |
| Selected Host tests | 15 passed, 0 failed | Context authority, run lifetime, meta dispatch, MCP operation boundary |
| Headless direct fixture | Script PASS, 23,146 ms, 6 model requests | Actual file, MCP call, and independently verified artifact |
| Headless planned fixture | Script PASS, 32,678 ms, 12 model requests | Both worker writes and Ready artifact observed; NOT sufficient to prove successful root integration |
| TUI startup/connect/model picker | PASS | Actual Windows PTY, local fixture credential entered through /connect |
| TUI /plan | PASS for plan-only boundary | Host plan_ready; both result files absent; zero workers and zero verified Evidence |
| TUI /harness | Shows reviewed plan | Domain, plan ID/revision, claims, criteria, reviewer count, and worker counts displayed |
| TUI /execute | PARTIAL / FAIL overall | Both workers completed with verified files; root integration failed |
| Reverify after integration failure | FAIL, promotion defect reproduced | blocked became ready without correcting the integration error |
| TUI exit | Exit code 0 | /exit returned from the actual PTY |
| Fixture shutdown | Exit code 0 | Local fixture stop endpoint and process handle |

The initial headless PASS must not be presented as full execution success. The later TUI and API evidence is stronger and exposes missing completion-gate coverage.

## Evidence

Pinned tools:

- .tools/bun-1.3.14/bun.exe
- .tools/verifier/Scripts/python.exe

Saved validation results:

- .tools/validation/restoration-phase15-gates.json
- .tools/validation/restoration-phase15-coordinator-typecheck.log
- .tools/validation/restoration-phase15-host-typecheck.log
- .tools/validation/restoration-phase15-coordinator-tests.log
- .tools/validation/restoration-phase15-host-lifetime-tests.log
- .tools/validation/restoration-phase15-real-flows.json
- .tools/validation/restoration-phase15-planned-flow.log
- .tools/validation/restoration-phase15-direct-flow.log
- .tools/validation/restoration-phase15-tui-plan-ready.json
- .tools/validation/restoration-phase15-tui-execute.json
- .tools/validation/restoration-phase15-tui-reverify-after-integration-failure.json
- .tools/validation/restoration-phase15-tui-audit.json

Headless scratch directories:

- Planned: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-dGB99J
- Direct: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-Mr7Y8c

TUI scratch directory: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-ughQf4

TUI session: ses_f8beeeaeaffeHwehZCf7rmjBXO
Run: run-ff74055b-758f-4bc7-9d2a-b9629cdef1a3
Plan: 46c2a9f8-d935-44ad-bec8-55fa3ef31c3f, revision 1

Observed TUI sequence:

1. Connect the configured Local fixture using its fake credential; select Fixture model.
2. Stage /plan and submit the fixture goal.
3. Query Host: planningState=plan_ready, workers=[], evidenceCount=0, readyEligible=false; neither output file exists.
4. Open /harness and observe the reviewed two-step plan.
5. Submit /execute through the TUI.
6. Both workers reach completed, evidenceCount=2, and both files contain exactly "fixture success" followed by a newline.
7. Root integration ends blocked with harness_error and the message below.
8. POST the existing harness/verify endpoint without changing code, configuration, or artifacts.
9. The same run becomes ready with readyEligible=true. This is a defect, not a successful recovery.

Observed integration error:

```text
Expected string, got undefined
  at ["info"]["model"]["id"]
```

No paid provider or real account credentials were used.

## Residual Risk and Required Follow-up

### 1. Root model-selection contract mismatch

session/tools.ts puts a full Provider.Model in extra.model. Task's integration adapter casts that value to PromptInput.model, whose required identifier is modelID. createUserMessage later forwards that absent modelID to the persisted model.id field.

Replace this unchecked cast with an explicit typed model selection at the Host boundary. Keep the full provider descriptor separate, preserve the exact provider/model/variant, and reject malformed selections before creating an integration message. Do not infer reasoning levels or model names.

### 2. Integration failure can be erased by verification

startIntegration records its exception in run.verification but not in the root execution-failure latch. The scheduler correctly treats terminal integration as settled, but verifyRoot can then verify completed file claims and overwrite that failure with Ready.

Settlement and successful completion must remain distinct. Latch non-repairable integration failures, require successful integration before root Ready on managed graphs, and do not let a synthetic session.completion observation clear that latch. Reverification must remain blocked until a real permitted recovery has completed.

### 3. Headless fixture does not prove integration success

The current script accepts correct files, worker model requests, and a Ready artifact. It does not require a successful root integration invocation or reject a prior unresolved terminal Host failure. Strengthen this fixture and add a failure-then-reverify test before treating its green result as a release gate.

### 4. Remaining interface observations

The TUI footer appeared behind the Host during plan_ready; /harness displayed the correct reviewed plan. Reproduce and inspect event-driven footer refresh separately. Legacy Build and OC labels remain visible. The TUI connect flow worked without the manual API instance-dispose workaround used in the previous phase.

### 5. Coverage limits

- This is not certification for every real provider, OAuth flow, reasoning option, or MCP server.
- These simple independent file fixtures are not evidence for every complex dependency graph or shared-file integration.
- Single-run timings and fake token accounting do not establish a performance or cost improvement.
- OS sandbox escape resistance, every process descendant, and Windows/Linux packaging were not re-certified.
- The broad restoration goal remains active; no completion claim or push was made.
