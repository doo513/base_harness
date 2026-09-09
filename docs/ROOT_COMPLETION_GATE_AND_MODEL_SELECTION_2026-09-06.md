# Root Completion Gate and Model Selection Restoration

Date: 2026-09-06
Status: Functional fixes verified; full promotion incomplete because a newly added test has TypeScript errors.
Repository: C:/Users/doo33/Downloads/base_harness

## Situation

Phase 15 restored detached worker lifetime. Actual TUI testing then exposed a root integration failure caused by an invalid model selection, followed by a more serious completion-gate defect: a verification request turned the same failed integration run into Ready without correcting the failure.

The old headless fixture accepted correct files and a Ready artifact without requiring a successful root integration call. Its green result did not prove full execution success.

## Reason

- The Host stored a full Provider.Model descriptor in Tool.Context.extra.model.
- The integration adapter cast that descriptor to PromptInput.model, which requires modelID rather than id.
- The root integration exception was stored in the displayed verification status but not in a terminal root failure latch.
- The scheduler correctly allowed a terminal failed run to settle, but verifyRoot incorrectly treated settlement as sufficient to attempt successful completion again.
- A generic successful tool observation could also clear the ordinary root execution-failure map.
- Verification fixtures need to distinguish actual successful integration from artifact existence and expected failures.

## Action

### Completion ownership

- Added a run-local rootExecutionFailure latch.
- Integration dispatch failures, integration exceptions, missing root repair executors, and root verification exceptions retain a terminal failure through blockRootExecution.
- Failure state retains its original typed source when an adapter reports a typed error before throwing a display error.
- Existing committed, independently verified worker changes remain intact.
- Managed graphs require successful root integration before root completion verification.
- A failed root execution rejects additional WorkGraph dispatch in that run.
- Later verifier snapshots and unrelated successful tool observations cannot clear the terminal latch.
- The latch is cleared by creating a new run, not by a synthetic completion observation or repeated verification request.

### Model selection

- Added ExecutionModelSelection with explicit providerID and modelID.
- Host tool contexts now keep the full provider descriptor and the execution selection in separate fields.
- Provider descriptors are converted once at the Host boundary.
- Integration validates its execution selection instead of casting a provider descriptor.
- Identifier values are preserved exactly; no model name, reasoning-level inference, or natural-language classifier was added.
- The existing variant is forwarded unchanged.
- Integration instructions now include a typed base-harness-root-integration-v1 marker. This is not Evidence or Ready authority.

### Test coverage

- Extended real Python verifier scenarios to include generic Host integration failure and a missing integration executor.
- Repeated manual, automatic, and completion verification after terminal failure must remain blocked.
- A successful read observation after that failure must not restore Ready.
- These negative cases assert that root verifier verification was not called.
- Headless planned fixtures now require an actual root integration model request.
- Added an expected integration-provider-failure fixture; correct worker files must not produce a Ready artifact in that case.
- Repeated the actual Windows TUI connect/model/reasoning/plan/execute path using an isolated local fixture.

Files changed:

- runtime/packages/coordinator/src/index.ts
- runtime/packages/base-harness/src/session/tools.ts
- runtime/packages/base-harness/src/tool/task.ts
- runtime/packages/base-harness/src/harness/model-selection.ts
- runtime/packages/base-harness/test/harness/model-selection.test.ts
- runtime/packages/coordinator/test/real-parallel-repair.test.ts
- runtime/script/fixtures/local-runtime.ts
- runtime/script/verify-real-host-flow.ts
- runtime/script/serve-local-runtime-fixture.ts

## Result

| Check | Result | Interpretation |
| --- | --- | --- |
| Coordinator typecheck | PASS, 2,060 ms | Production coordinator and its tests compile |
| Host typecheck | FAIL, exit 2 | Three diagnostics in the new model-selection test's typed expect comparisons |
| Coordinator test suite | 37 passed, 0 failed | Includes real Python integration-failure/reverification cases |
| Selected Host tests | 19 passed, 0 failed | Includes execution model selection and prior boundary tests |
| Actual headless planned flow | PASS, 34,522 ms | 13 requests, including root integration; both files correct and Ready produced |
| Actual headless integration-failure flow | Expected failure verified, 31,040 ms | Child exit 1, both worker files correct, root integration attempted, no Ready artifact |
| Actual headless direct flow | PASS, 22,276 ms | 6 requests, correct file, Ready produced |
| Actual TUI connect/model selection | PASS | Credential and model selected through TUI dialogs |
| Actual TUI reasoning selection | PASS for fixture | Service-supported max selected and retained in observed requests |
| Actual TUI plan-only boundary | PASS | plan_ready, no workers, no verified Evidence, both output files absent |
| Actual TUI execute | PASS | Both workers completed; successful root integration; Host reached Ready |
| Actual TUI /harness | PASS for displayed completion | READY (adaptive), both completed workers, Evidence 4 |
| Actual TUI exit | Exit code 0 | Normal /exit |
| Local fixture shutdown | Exit code 0 | Bound fixture process terminated |

There are 56 passing runtime tests, but the Host typecheck is not green. The full restoration goal remains active.

## Evidence

Runtime tools:

- Bun 1.3.14: .tools/bun-1.3.14/bun.exe
- Python verifier: .tools/verifier/Scripts/python.exe

Validation files:

- .tools/validation/restoration-phase16-gates.json
- .tools/validation/restoration-phase16-coordinator-typecheck.log
- .tools/validation/restoration-phase16-host-typecheck.log
- .tools/validation/restoration-phase16-coordinator-tests.log
- .tools/validation/restoration-phase16-host-boundary-tests.log
- .tools/validation/restoration-phase16-real-flows.json
- .tools/validation/restoration-phase16-planned-flow.log
- .tools/validation/restoration-phase16-integration-failure-flow.log
- .tools/validation/restoration-phase16-direct-flow.log
- .tools/validation/restoration-phase16-tui-plan-ready.json
- .tools/validation/restoration-phase16-tui-execute.json
- .tools/validation/restoration-phase16-tui-audit.json

Headless scratch directories:

- Planned: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-sc5kZI
- Integration failure: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-rkcubh
- Direct: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-1MPbuK

TUI scratch directory: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-jerMII

TUI session: ses_f8bdad7a1ffeNQAcoH2lAelD04
Run: run-e8bd3f9a-f21c-4888-8388-7a886bd2fe4c
Plan: 27e202ef-ec62-45ef-a250-054712df6164, revision 1

TUI procedure:

1. Launch the actual attach TUI against an isolated local Host and stdio MCP fixture.
2. Use /connect to enter a fake fixture credential.
3. Select Fixture reasoner in the model picker.
4. Select max from the model's supplied Provider default/high/max options.
5. Stage /plan and submit the fixture goal.
6. Query the Host and confirm plan_ready with neither output file present.
7. Submit /execute through the TUI.
8. Observe two completed workers, both exact file contents, and a successful root integration request.
9. Query Host Ready, then open /harness and observe READY (adaptive).
10. Exit the TUI and stop the fixture.

Model-request evidence:

- All 11 execution/review requests used fixture-reasoner with reasoningEffort=max.
- Those requests include GoalContract review, PlanSpec review, both workers, and root integration.
- A separate title-generation request used the configured small model, fixture-model, without an effort override.
- This distinction does not constitute loss of the execution model selection.

## Residual Risk

### New test type errors

The new model-selection.test.ts passes at runtime but its expect(...).toEqual(...) arguments use plain strings where the matcher requires branded ProviderV2.ID and ModelV2.ID values.

Diagnostics are at line 7 (two fields) and line 14. Correct the test expectation types or compare explicitly observed string scalars; do not weaken the production selection contract. This correction was not applied in this phase.

### Remaining interface work

- At plan_ready, the footer still appeared to retain direct even though the Host reported planned/plan_ready.
- The full /harness overlay showed the correct final Ready state.
- Host-generated integration instructions appear as a raw JSON conversation message; they should be rendered or hidden as internal execution context rather than presented like a user request.
- Build and OC legacy display labels remain.
- The observed /plan and /execute path reused a run ID. Separation into distinct planning and execution run records, if required by the retained Kernel contract, still needs a focused audit.

### Scope of the evidence

- Local deterministic providers were used; no paid provider, real subscription, or real account credential was used.
- Passing fixture reasoning inheritance does not certify every provider's OAuth or capability discovery.
- The two-file graph does not cover every shared-file integration or arbitrary complex task.
- Single-run timings and fixture token counts are not performance or cost benchmarks.
- Linux sandbox behavior, packaging, every process descendant, and the entire repository-wide suite were not re-certified.
- Python evidence promotion policy, sidecar wire protocol, Overlay attestation, memory lifecycle, and net_monitor.py were not changed.
- No git, commit, or push was performed.
