# Restored Host flow baseline, 2026-09-05

## Situation

The restored Host could start, but independent file Claims referenced an
unregistered verifier. Planned work could remain in the direct workspace phase.

## Reason

A visible TUI and mocked verifier tests do not demonstrate execution correctness.
The execution path must cross the Kernel and Coordinator and obtain independent,
Claim-specific evidence before completion.

## Action

- Added explicit direct-to-planning transitions without natural-language triggers.
- Added bounded independent file predicates: exists, content_contains,
  content_equals, and sha256.
- Bound child command checks to the materialized candidate workspace.
- Required the complete root Claim/Criterion set for root completion.
- Required an actually issued child attestation before recording candidate commit.
- Added a local model HTTP and stdio MCP fixture using the real Host and Python sidecar.
- Separated non-code boundary failures from automatic implementation repair.
- Added Host-error feedback to TUI credential and MCP requests.
- Publish only service-reported or explicitly configured native reasoning efforts.
- Reject unsupported or overwritten explicit efforts at the Host request boundary.

## Result

Both headless execution and an interactive TUI attached to the same real Host
completed a local fixture task: six model requests, a stdio MCP echo call, exact
generated file bytes, and an independently issued Ready artifact. TUI credential
entry and MCP disconnect/reconnect reached the Host; leaving the TUI preserved the
Host's completed state. Fixture processes were explicitly stopped afterward.

The model endpoint and credential are deterministic local test fixtures, not an
external LLM or an OAuth login. The interactive pass exposed missing reasoning
capabilities despite configured variants. This follow-up addresses that boundary
and adds native-value and pre-provider rejection tests.

The preceding pass had 39 passing TypeScript tests and a passing TUI typecheck.
Python passed 45/46 tests; the remaining legacy test expected an unknown failure
to consume automatic repairs. It now asserts a non-repairable failure with zero
repair count while retaining the independent child-scope continuation check.
The follow-up passed 46 Python tests, 49 TypeScript tests, and Host/TUI typechecks.
A fresh interactive TUI pass sent exact max in all four root requests and obtained
independent Ready; the subsequent headless pass also succeeded.

The next candidate-integrity pass keeps the verification workspace until commit,
checks bytes before and after observation, delays evidence promotion until those
checks pass, and requires an independently validated commit receipt.

Phase6 passed five typechecks and the direct headless fixture, but its worker
validation remained incomplete: Python 52 passed / 2 failed, TypeScript 50 passed /
8 failed plus one unhandled persistence error. The failures exposed differing
Windows path/descriptor ctime semantics, untracked asynchronous snapshot writes,
and a missing hello protocolVersion in the new test-only ACK responder.

The follow-up retains same-accessor ctime checks, adds run-scoped ordered atomic
snapshot writes with drain barriers, fixes actual run-ID candidate projection,
and implements the fixture handshake. Phase7 passed 56 Python tests, 61 of 64
TypeScript tests, and five package typechecks. The remaining three ACK tests
timed out with Bun's asynchronous rejection matcher; equivalent standalone
subprocess requests returned the expected protocol/conflict errors immediately.

The phase8 follow-up awaits the rejection before asserting its properties, without
relaxing the client protocol. Candidate publication now stages all files and durable
backups before mutation, performs renames only within the workspace filesystem,
and retains the journal if rollback cannot safely restore the original state.
Recovery checks current bytes and does not deliberately overwrite a detected
external edit. Injected I/O tests cover cross-device constraints, partial publication,
failed rollback, staging collisions, and tampering.

Phase8 command exit codes and logs, rather than this implementation description,
determine the result of the follow-up. Full OS isolation and atomic compare-and-swap
against arbitrary concurrent external writers remain outside this evidence.

Phase8 passed 56 Python tests, 69 TypeScript tests, five package typechecks, and
the real Host/model/MCP/Ready fixture. One POSIX mode test was skipped on Windows.
One parallel Coordinator test failed. Repeated diagnostics reproduced a race:
candidate materialization copied another worker's short-lived publication file,
which disappeared during copy or held a Windows rename open.

The phase9 change serializes candidate workspace copying and publication through
the same store queue while leaving worker execution parallel. Typed copy failures
are attributed to workspace/harness, not to the independent verifier. New tests
hold copy/publication barriers and exercise actual Python verification with three
workers, same-session local repair, and repair exhaustion.

The phase9 logs and exit-code artifact determine whether those new gates pass.

Phase9 passed 56 Python tests, 76 TypeScript tests, five package typechecks, and
the direct Host/model/MCP/Ready fixture. Its two remaining failures were the new
real-verifier repair/exhaustion scenarios. Diagnostics showed that a rejected
worker's verdict survived into a reopened scope and an independent worker's
action.open response.

Phase10 separates rejection/runtime failures and repair budgets per scope, clears
transient client fields between status snapshots, and keeps each worker's rejection
for repair routing and final blocking. Root verification still checks every
unresolved runtime failure and all mandatory Claims. The wire protocol remains v4;
new per-scope manifest fields are additive. Verification command output determines
whether the new restoration gates pass; this is not a full completion certificate.

## Evidence

- runtime/script/verify-real-host-flow.ts
- runtime/script/serve-local-runtime-fixture.ts
- tests/test_restored_verification_boundary.py
- .tools/validation/real-host-flow.result.json
- .tools/validation/tui-host-flow.result.json
- .tools/validation/restoration-phase4-python.log
- .tools/validation/restoration-phase4-typescript-tests.log
- runtime/packages/base-harness/test/provider/reasoning-capabilities.test.ts
- runtime/packages/base-harness/test/provider/reasoning-request.test.ts
- .tools/validation/restoration-phase5-tui-host-flow.result.json
- runtime/packages/coordinator/test/real-candidate-integrity.test.ts
- runtime/packages/workspace/test/candidate-integrity.test.ts
- runtime/packages/verification/test/candidate-commit.test.ts
- runtime/packages/workspace/test/persistence.test.ts
- .tools/validation/restoration-phase6-findings.json

The interactive fixture exposes a real Host URL so the TUI can attach without
creating a second Coordinator or verifier owner. Its credential is test-only.

## Residual Risk

- External OAuth and real-provider semantics have not been proved by this fixture.
- The phase5 real TUI pass confirmed exact max reasoning, Host MCP reconnect, and independent Ready; external provider behavior is still unproved.
- Numeric reasoning budgets are not represented as invented named effort levels.
- Strict OS confinement and all candidate snapshot race boundaries are not certified here.
- This is partial restoration evidence, not a completed release or a full goal audit.

## Phase 11: worker failure boundaries and root-owned status

### Situation
- The phase 10 gate recorded 61 passing Python tests, 79 passing TypeScript tests, one skipped POSIX-only test and one failing protocol-fixture test.
- Real parallel execution, same-session repair, repair exhaustion, five package typechecks and the real local Host/MCP/Python completion flow passed that gate.
- The remaining fixture copied the root scope identifier into child candidate/action replies.
- Worker execution catches still defaulted to implementation errors and used the latest shared verifier status; repair preparation occurred outside the cleanup boundary.

### Reason
- A child failure must not become root completion authority or replace a still-active run.
- Provider and verifier failures are not permission to repair implementation code.
- A failed repair handshake or an executor that returns without verification must release its scheduling slot without committing its overlay.

### Action
- Keep child verdicts on worker records and project only aggregate observations into root verification status.
- Retain original Host-observed model/tool failure provenance before task output is flattened into a display string.
- Use one bounded worker lifecycle for initial execution, same-session repair setup, verified completion and slot cleanup.
- Reopen the verifier scope before changing the workspace candidate state; reject missing or unsuccessful reopening acknowledgments.
- Preserve non-repairable failures, reject unverified executor returns, and keep independent units runnable after failure.
- Retain drain requests arriving during an existing scheduler pass.
- Refuse root completion while a non-repairable Host failure remains; a synthetic completion observation cannot count as provider recovery.
- Correct the test fixture response identities without relaxing production NDJSON identity validation.
- Extend real-Python tests with blocked dependencies, provider failures, reopen failures, unverified returns, workspace conflicts and generic Host setup failures.

### Result
- Implementation changes are applied in one patch phase.
- Phase 11 tests and typechecks are pending at the time of this report; do not interpret this section as a passing gate.
- Generated phase 11 validation logs and gate records are the authoritative execution results.

### Evidence
- Prior baseline: `.tools/validation/restoration-phase10-gates.json` and `restoration-phase10-typescript-tests.log`.
- Targeted behavioral proof: `runtime/packages/coordinator/test/real-parallel-repair.test.ts`.
- Protocol boundary regression: `runtime/packages/verification/test/client.test.ts` and `scope-status.test.ts`.
- Current validation output is recorded under `.tools/validation/restoration-phase11-*`.

### Residual Risk
- These fixtures use a local model endpoint, not an externally authenticated subscription provider.
- Full process-tree cancellation, strict verifier OS confinement and external-writer TOCTOU resistance remain separate audit items.
- A shared-model semantic mistake or an incomplete GoalContract is not ruled out by a passing execution gate.
- `net_monitor.py` is unchanged; no Git operations or remote publication are performed.

## Phase 12: settlement, trusted continuation and reviewed-plan execution

### Situation
- Phase 11 produced 61 passing Python tests, 86 passing TypeScript tests, one skipped POSIX test and one failing root-integration completion wait.
- The diagnostic confirmed blocked/model_provider_error, no active workers and Ready=false, while the completion promise remained pending.
- The old phase 11 aggregate gate lost native exit codes through a PowerShell scriptblock scope; restoration-phase11-audit.json, not that all-green aggregate, records the actual incomplete result.
- The Host prompt entry invokes KernelHost.openRun for root integration too; it could reset an executing Kernel to contract_building.
- KernelHost saved the reviewed PlanSpec but dispatched the original graph object, and caller mutation could change a pending graph.

### Reason
- A failed integration is settled, not ongoing work; independent workers must still be allowed to finish.
- Internal integration and repair must retain the accepted contract, plan and original execution context without accepting authority from prompt text.
- The reviewed plan and the graph that reaches the scheduler must agree.

### Action
- Recognize terminal integration outcomes after in-flight worker checks in the scheduler.
- Scope root continuation to a private Coordinator AsyncLocalStorage lease and revoke it after the executor returns.
- Preserve Kernel planning state only for a matching live internal continuation; mismatched workspace/run state fails closed.
- Keep integration and repair prompt guidance on the existing contract and plan.
- Clone accepted graphs, bind reviewed plan identities/steps to their graph, recheck file basis and dispatch the reviewed graph.
- Add deterministic settlement and planning-boundary tests.
- Extend the local HTTP model fixture with contract/plan review and separate worker responses, enabling a real planned Host flow and interactive TUI exercise.

### Result
- Source changes are applied as one patch phase.
- Phase 12 validation is pending when this section is written. Generated logs and result artifacts record actual outcomes, including any failures.
- No external paid model, account login, Git operation or net_monitor.py change is part of these fixtures.

### Evidence
- Prior diagnosis: .tools/validation/restoration-phase11-root-failure-diagnostic-retry.log.
- Scheduler regression: runtime/packages/coordinator/test/restored-settlement-boundary.test.ts.
- Kernel boundaries: runtime/packages/kernel-host/test/restored-planning-boundary.test.ts.
- Real direct/planned Host flow: runtime/script/verify-real-host-flow.ts, with --planned for the latter.
- Interactive shared Host fixture: runtime/script/serve-local-runtime-fixture.ts.

### Residual Risk
- Private continuation propagation through the real Effect-based Host must be proven by the planned runtime fixture, not only unit tests.
- Directory/symlink planning-basis coverage and complete process-tree/OS confinement remain separate audit items.
- Local fixture credentials do not prove external OAuth service compatibility.

## Phase 13: real meta-review scope and failure provenance

### Situation
- Phase 12 passed 61 Python tests, 106 TypeScript tests (one platform skip), seven typechecks and the real direct Host flow.
- The real planned Host fixture failed before any meta-review model request. Workspace startChild treated meta-review as an implementation worker and rejected it without a WorkUnit.
- KernelHost retried all reviewer exceptions and eventually mislabeled Host dispatch errors as model protocol errors.
- A live attached TUI authenticated to the local fixture, selected fixture-reasoner/max, toggled MCP off/on, created the requested file and displayed Ready (adaptive). TUI exit returned zero.
- The follow-up Host query after TUI exit found the fixture server already terminal; this does not prove Host persistence after UI exit in this repetition.

### Reason
- A planning reviewer is neither an implementation worker nor a source of completion evidence.
- Authority to dispatch reviews must come from a private Host context, not an Actor-provided role or coordinatorDispatch flag.
- Only invalid returned review schemas warrant the bounded schema-repair retry; a Host or provider failure must retain its source.

### Action
- Add a fresh root-owned meta_review scope before WorkGraph dispatch, with read/list/glob/grep only and no Overlay write or candidate rights.
- Preserve the root phase and contract on reviewer exit; review completion is not worker completion.
- Add a Host WeakMap dispatch lease, validated before child creation and revoked after completion or failure.
- Keep selected provider/model/variant inheritance through the existing Task runtime.
- Report review Host/model/tool failures directly to Coordinator without sending review results as verifier observations.
- Preserve the first typed review failure against generic Task wrappers and late events; fail closed until a new user run.
- Limit automatic schema repair to invalid returned review output, not execution failures.
- Add workspace, Host dispatch, Kernel review and Coordinator failure-boundary regression tests.

### Result
- Changes are applied in one patch phase. Phase 13 source verification is pending at document creation.
- Generated restoration-phase13 gate records and real-host-planned-flow.result.json record the actual subsequent outcomes, including failures.
- The live TUI used a fake credential and local model/MCP services, not a paid provider or subscription account.

### Evidence
- runtime/packages/workspace/test/meta-review-boundary.test.ts
- runtime/packages/base-harness/test/harness/meta-review-dispatch.test.ts
- runtime/packages/kernel-host/test/meta-review-failure-boundary.test.ts
- runtime/packages/coordinator/test/meta-review-failure-boundary.test.ts
- .tools/validation/restoration-phase12-gates.json
- .tools/validation/restoration-phase13-tui.json

### Residual Risk
- Planned Host execution must pass the real local model + MCP + Python fixture; isolated scope tests are not sufficient.
- MCP operation classification during planning, complete process-tree isolation and directory/symlink plan-basis coverage remain audit targets.
- Shared-model semantic mistakes, incomplete contracts and external OAuth compatibility are not certified by these fixtures.
- No Git operations, remote publication or net_monitor.py changes are included.
