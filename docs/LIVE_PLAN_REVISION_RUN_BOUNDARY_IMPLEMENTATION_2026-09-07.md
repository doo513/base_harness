# Live Plan Revision Run Boundary

Date: 2026-09-07
Status: Partial. Revised attached execution can reach real Ready; persistence and liveness gates remain open.

## Situation

A live attached Host reused an existing planning run when ordinary text revised
its plan. Kernel plan revision increased, but Coordinator.openRun() retained
the previous goal/source/policy and updated only context. A fresh local Host
did not have that in-memory run, producing a different lifecycle.

The previous fixture repeated the same goal. It could not establish whether
changed requirements and model settings reached execution correctly.

## Reason

A plan revision must not inherit the old run's observations or verification
authority. The chosen implementation opens a fresh planning run for a typed
Host-owned revision while preserving the previous reviewed plan as history.
This is now an explicit lifecycle policy rather than merely a run-ID assertion.

## Action

- Added an optional Host-owned revisesPlan link to Coordinator input and status.
- Kernel derives that link from its reviewed plan, not actor-supplied metadata.
- Coordinator validates the prior run and contract hash before replacing a live, unexecuted planning run.
- Archived the prior planning snapshot and closed its verifier before opening a new run.
- Added a same-session revision transition guard and Kernel opening guard.
- New runs construct fresh goal/source and verification state from the new request.
- Extended the independent-verifier test with changed goal/predicate and concurrent revision rejection.
- Extended local model fixtures to change expected output content and native reasoning effort from max to high.
- Kept plan-only mutation denial, explicit execute, independent verifier v4, candidate attestation and root-only Ready.
- Preserved first-attempt failures and phase-specific result copies rather than replacing them with a green rerun.

## Result

| Gate | Result |
| --- | --- |
| KernelHost tests | 45 passed, 0 failed; 187 expectations |
| Targeted Coordinator tests | 16 passed, 1 failed; 151 expectations |
| Total targeted tests | 61 passed, 1 failed |
| Coordinator, KernelHost, Host, TUI typechecks | Passed |
| Revised verifier goal source | Confirmed before the persistence assertion failed |
| Initial attached fixture | Failed at Host readiness; no clients or model requests |
| Initial local positive fixture | Timed out during initial planning after contract and MCP echo |
| Local revised-plan Provider-failure fixture | Passed; updated outputs, high effort, blocked/no Ready |
| One attached repeat, without source changes | Passed through changed revision, cross-directory execute and real Ready |

The repeat does not erase the initial failures and is not evidence that the
intermittent startup/request wait is fixed.

### Successful attached changed-requirement execution

- Session: ses_f83f97c72fferJrDhKNG9xTErc
- Plan: db9fdea1-cdb0-4a02-9261-3cc521ff86b0
- Original planning run: run-51ba92f5-575e-4fb8-9147-fe9dd2d1a44c
- Revised planning run: run-91bc04e7-b65e-43bb-9e50-e219f599728c
- Execution run: run-becf9dc7-19d6-4339-a10a-f0175fe505bb
- Plan revision: 1 to 2.
- Original contract hash: dcf009466af2a507e20a571237bfddf0d5bfa48f65becf34e93aa53942958e7b
- Revised contract hash: 9cc15b5299457d7ec1752e281f7bde768518164bcae11da952826352fbec6772
- Updated expected output: fixture revised success followed by a newline.
- The revised goal was retained through execution.
- The model pipeline used max before revision, then high for revised planning, both workers and root integration.
- Both workers completed and the real verifier produced Ready with four evidence references.
- Wrong-plan execution was rejected without an additional model call.
- Execute ran from another directory without --dir.
- Ready artifact: C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-XNZ4h2\state\base-harness\runs\2f0aa113eb895355-d583b94e\artifacts\d5\d54fe7566ce8e2113910740205c07ba38f296014029a1a275ea02738160a5f1f.json

### Successful negative execution

- Session: ses_f83fd913bffezfaJo9JMSVyueD
- Revised planning run: run-9e88dd7a-8cbd-48fa-a88c-385e0d7561e4
- Execution run: run-5839e2ff-8e5d-4da5-bbb6-43458fd0653c
- Both worker files contained the changed requested output.
- Root Provider failure produced model_provider_error/blocked and no Ready.
- Verified worker commits were preserved as intended.

## Failed Persistence Gate

The new revised-run test fails because the persisted snapshot lacks
revisesPlan, even though the in-memory status contains it.

RunRepository.persist() builds an explicit field list. The new field was
added to Coordinator status but not to that persistence serializer. This is
an implementation omission, not a reason to remove the assertion.

The same test also expects a plaintext goal in the persisted Coordinator
snapshot. That expectation is wrong: the existing format deliberately stores
goalDigest instead. The follow-up must retain that privacy boundary and compare
SHA-256(nextGoal), not add plaintext goals just to satisfy the test.

No second corrective source patch was applied in this turn.

## Liveness Evidence and Limits

The initial attached fixture did not pass its readiness probe and had no model
completion requests. Its captured stdout/stderr were empty, so there is not
enough evidence to assign a cause.

The initial local positive fixture reached an accepted GoalContract, completed
harness_contract and fixture_echo, then remained at planning_decision. Four
model requests were recorded; the next WorkGraph request was not observed.
The fixture's explicit 90-second bound terminated its CLI, which exited 143.

The complete test process was terminal before one attached diagnostic repeat
was started. The original results were retained. The repeat succeeded without
a source change, indicating that failure is not consistently reproducible.
This does not establish whether the cause is transport, startup, scheduling
or another runtime boundary, and no timeout was increased to conceal it.

The local positive changed-requirement Ready path was not completed in this
turn. The negative local case and attached repeat must not be relabeled as
that missing positive gate.

## Evidence

- .tools/validation/restoration-phase26-gates.json
- .tools/validation/restoration-phase26-coordinator-tests.log
- .tools/validation/restoration-phase26-kernel-host-tests.log
- .tools/validation/restoration-phase26-coordinator-typecheck.log
- .tools/validation/restoration-phase26-kernel-host-typecheck.log
- .tools/validation/restoration-phase26-host-typecheck.log
- .tools/validation/restoration-phase26-tui-typecheck.log
- .tools/validation/restoration-phase26-attached-changed-revision.result.json
- .tools/validation/restoration-phase26-local-changed-revision.result.json
- .tools/validation/restoration-phase26-local-changed-revision-provider-failure.result.json
- .tools/validation/restoration-phase26-attached-changed-revision-repeat.result.json
- .tools/validation/restoration-phase26-handoff.json

The corresponding .log files retain command output. Previous fixture results
were copied to phase26-<case>.previous.result.json before shared fixture paths
were reused.

## Residual Risk and Next Actions

1. Persist revisesPlan without changing the existing Coordinator schema version or storing plaintext goal content; correct the goalDigest test expectation.
2. Rerun the complete revised-run verifier test and the positive local changed-requirement fixture.
3. Trace Host readiness and the model/tool transition stall using bounded diagnostics; do not claim a successful repeat fixes the original wait.
4. Same-session recovery/discard after an interrupted plan revision remains unsupported and fail-closed.
5. The new transition guard does not certify every cancellation/crash interleaving or all platforms.
6. These are local deterministic provider/MCP fixtures, not live OAuth/subscription certification.
7. TUI typechecking is not a new interactive TUI certification.
8. Existing same-OS-account HMAC limits and common-mode model reasoning risks remain.
9. No git commands, commits or push were performed. net_monitor.py was not edited.

