# Task Metadata Diagnostic Follow-up

## Situation

The task-running-metadata test remained reproducibly failing after forwarding the structured explore selector through contract admission. The adjacent busy/idle test passed in isolation.

## Reason

Automatic exploration was a possible competing consumer of the scripted task response. A separate possibility is that metadata arrives before its tool-call state is registered.

## Action

- Set orchestration.exploration=manual only in this fixture. The explicit read-only explore task remains enabled.
- Added immediate failure diagnostics for an errored task part or errored build assistant instead of waiting only for running metadata.
- Kept the real Kernel/Orchestration and tool execution path; no execution timeout increase or admission bypass was added.
- Ran the two isolated tests in a separate process under a 60-second parent deadline.
- Inspected tool metadata update, tool-call state creation/transition, and agent naming code. No production event-pipeline patch was made in this follow-up.

## Result

- 1 passed, 1 failed, 57 filtered out; 2 assertions, 12.43 seconds.
- The task metadata timeout persisted. Disabling automatic exploration was insufficient to resolve it.
- The new early-error checks did not fire.
- Busy/idle passed again.
- The parent deadline did not fire, and the child process exited with code 1.
- Host typecheck passed with exit code 0.
- The task metadata problem is not resolved.

## Evidence

- Stdout: .tools/validation/task-metadata-explicit-1788859258583.stdout.log.
- Stderr: .tools/validation/task-metadata-explicit-1788859258583.stderr.log.
- Diagnostic wrapper session 27441 reported stopped=true, timedOut=false, exitCode=1.
- Host typecheck session 67179 exited 0.
- Companion: TASK_METADATA_DIAGNOSTICS_2026-09-08.json.
- Inspected SessionProcessor.updateToolCall returns without applying an update when readToolCall finds no registered part. The later tool-call transition preserves metadata only when the part is already running.
- That code path is a possible lost-update mechanism, not a confirmed explanation of this particular timeout.
- Actual call IDs and stored part-state observations are still needed to distinguish early metadata, ID mismatch, and absence of the expected assistant/tool part.

## Residual Risk

- Do not classify the metadata race as reproduced solely from this timeout and source inspection.
- The next diagnostic should record bounded, non-secret role/call-ID/status/metadata-presence information at failure.
- A scoped fixture typecheck pass does not prove runtime correctness, TUI stability, or full-suite success.
- No real-account model call, new production completion permission, Git operation, or net_monitor.py modification was performed.

## Follow-up: Observed Tool State and Second Admission Boundary

- Added bounded role, message/call ID, tool state, and metadata-presence diagnostics. No prompt, arbitrary tool output, or credential contents were included.
- Fresh isolated result: 1 passed, 1 failed, 57 filtered out; 15.94 seconds. Host typecheck passed.
- The task call was already in error with no child-session metadata. A later build assistant had started another model request.
- The test inspected only the latest build assistant, which hid the earlier errored task from its early-error check.
- Source inspection located a second contract-admission call inside ToolRegistry.execute that still drops structured subagent_type. This can reject pre-contract explore even though SessionTools now forwards that selector.
- The next patch is restricted to passing the same typed selector at this second boundary and selecting the latest task-bearing assistant in the diagnostic. Existing Kernel, Orchestration, and TaskTool permission checks must remain.
- A speculative early-metadata buffer is not justified by the observed failure and will not be added as this fix.
- The production Registry correction has not yet been applied or tested; the timeout remains unresolved at this revision.
- Latest stdout: .tools/validation/task-metadata-observation-1788859650652.stdout.log.
- Latest stderr: .tools/validation/task-metadata-observation-1788859650652.stderr.log.

## Follow-up: Registry Role Forwarding Applied

### Situation
The Registry's second contract-admission check did not forward the structured task role, despite the earlier SessionTools boundary forwarding it.

### Reason
Both execution boundaries must evaluate the same task role without bypassing Kernel or Orchestration permissions.

### Action
- Forwarded a string subagent_type for task calls through the Registry admission guard.
- Preserved the Orchestration guard and TaskTool permission checks.
- Changed the diagnostic to inspect the latest task-bearing build assistant, rather than a later empty assistant.
- Ran the bounded task/busy-idle pair, the contract-admission tests, and Host typecheck.

### Result
- Contract admission: 8 passed, 0 failed, 52 assertions, 1.221 seconds.
- Host typecheck: exit 0.
- Task/busy-idle integration: 1 passed, 1 failed, 57 filtered out, 2 assertions, 11.77 seconds.
- Task metadata still fails. The diagnostic now detects the earlier failed task promptly, but its catch wrapper discards the underlying error and reports only poll_failed.
- Registry forwarding is implemented; resolution of the integration failure is NOT established.

### Evidence
- Stdout: .tools/validation/registry-task-admission-1788859934717.stdout.log.
- Stderr: .tools/validation/registry-task-admission-1788859934717.stderr.log.
- Integration session 37818: child PID 15392, stopped=true, timedOut=false, exitCode=1.
- Contract/typecheck session 53689: REGISTRY_ROLE_GATE tests=0 typecheck=0.
- Observed one model call and an errored task with no child-session metadata, followed by an empty build assistant.

### Residual Risk
- Next correction: preserve a bounded, redacted underlying diagnostic reason before changing more execution logic.
- No metadata buffer or permission relaxation is justified by this result.
- The watchdog did not fire; process-tree termination was not exercised.
- Full-suite success and independent real-user stability remain unverified.
- No Git operations or net_monitor.py changes were made.

## Follow-up: Underlying Task Error Preserved

### Situation
The diagnostic wrapper reported poll_failed and hid the task failure that preceded metadata creation.

### Reason
A metadata timeout alone cannot distinguish a state-transition defect from an execution-policy rejection.

### Action
- Preserved the first line of the underlying synthetic-fixture error, limited to 1024 characters.
- Redacted common authorization and named-secret forms; did not include stacks or nested payloads in the observation.
- Re-ran the bounded task/busy-idle pair and Host typecheck.
- Located the exact throw site in workspace/src/orchestration.ts.

### Result
- Integration: 1 passed, 1 failed, 57 filtered out, 2 assertions, 12.29 seconds.
- Actual reason: Task failed before running metadata: Exploration is allowed exactly once before planning.
- The throw occurs when root.phase is not exploration, before the exploration scope is created.
- This does NOT establish that exploration previously ran once; the message is broader than the actual predicate.
- Host typecheck passed.
- Task metadata remains unresolved. No metadata-buffer or production permission-policy change was made.

### Evidence
- Stdout: .tools/validation/task-error-reason-1788860346416.stdout.log.
- Stderr: .tools/validation/task-error-reason-1788860346416.stderr.log.
- Integration session 2863: PID 33744, stopped=true, timedOut=false, exitCode=1.
- Host typecheck session 1317: exitCode=0.
- Source predicate: runtime/packages/workspace/src/orchestration.ts:644-646.
- One model call was observed; the task was already errored without child metadata.

### Residual Risk
- The earlier diagnostic-only exploration=manual override may conflict with explicit exploration admission.
- Next patch should remove that temporary override and re-run the normal fixture policy before changing production state transitions.
- The two role-forwarding fixes remain; they were not both present before the temporary override was introduced.
- The current evidence does not prove the original fixture will pass after restoring default policy.
- This is fixture diagnostics, not independent user validation or Harness Evidence.

## Follow-up: Default Policy and Missing Explicit Exploration Transition

### Situation
The diagnostic-only manual exploration override was removed from the prompt fixture.

### Action
- Restored useServerConfig(providerCfg), preserving the role-forwarding fixes and bounded error diagnostics.
- Re-ran the isolated pair and Host typecheck.
- Investigated the reproducible PHASE_VIOLATION through Coordinator initialization and Workspace startChild.

### Result
- Integration: 1 passed, 1 failed, 57 filtered out, 2 assertions, 12.90 seconds.
- The same exploration phase error remained; the temporary fixture override was not its sole cause.
- Host typecheck passed.
- Coordinator.openRunState initializes Workspace with exploration=manual. Workspace.beginPrompt consequently initializes phase=direct.
- Workspace.startChild(explore) only accepts phase=exploration; no transition for explicit pre-contract exploration is present at that boundary.
- Do not replace the Coordinator default with always-explore: that would force unnecessary exploration for direct work.

### Evidence
- Stdout: .tools/validation/task-default-policy-1788860519558.stdout.log.
- Stderr: .tools/validation/task-default-policy-1788860519558.stderr.log.
- Integration session 82160: PID 21288, stopped=true, timedOut=false, exitCode=1.
- Host typecheck session 37424: exitCode=0.
- Coordinator initialization and Workspace beginPrompt/startChild establish the mismatch.
- Workspace.finishChild moves successful exploration to planning and failed exploration to blocked.

### Residual Risk
- Next production patch: a typed explicit exploration transition limited to the root before contract/planning, retaining read-only tools and a single-exploration admission latch.
- Cover duplicate/concurrent exploration, wrong parent, post-contract direct work, and terminal phases; do not merely relax the existing phase check.
- Existing startChild's running-scope shortcut must not bypass exploration identity checks.
- Task metadata and full-suite completion remain unresolved.

## Resolution Follow-up

The explicit root exploration transition is now implemented. The metadata pair passed (2/2), and the broader prompt/snapshot/contract group passed (54 passed, 14 skipped, 0 failed). Workspace targeted tests (20/20) and Workspace/Host typechecks passed. See EXPLICIT_EXPLORATION_ADMISSION_REPAIR_2026-09-08.md for bounds and residual risks. Earlier failed attempts above are retained as history, not the latest outcome.

