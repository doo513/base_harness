# TUI execution revalidation, presentation alignment, and restart gap

Date: 2026-09-08
Status: Partial progress; full product completion and promotion are not established.
Classification: diagnostic_only. This report and its JSON companion grant no Evidence or Ready authority.

## Situation

The phase36 plan-persistence and runtime-finalizer changes needed an actual native Windows TUI check. The phase37 interactive attempt ended at its ten-minute fixture deadline after producing a reviewed plan, but before explicit execution. That timeout remains a failed validation attempt, not proof that an execution request failed.

## Reason

The product must keep one Host-controlled execution path while making planning, execution, and independently verified completion understandable in the TUI. A passing local fixture is useful but does not establish live-provider usability, general complex-task performance, or restart continuity.

## Action

1. Used Bun 1.3.14 and the pinned real Python verifier with isolated local model/MCP fixtures. No paid model calls or external OAuth login was performed.
2. Created a plan headlessly, interrupted a revision, restarted the Host, and attached the native Windows TUI to the same session.
3. Discarded the interrupted plan through typed TUI control without a model call, enabled one-shot planning, and submitted a new request.
4. Confirmed that the reviewed new plan had no result files and no Ready.
5. Submitted a wrong plan ID; the TUI displayed PLAN_ID_MISMATCH / HTTP 400, and the planning run, revision, and absent result files were unchanged.
6. Executed the exact reviewed plan ID. Two WorkUnits completed, the final file contents matched their predicates, and the real Python verifier issued root Ready with both required Claims and Criteria verified.
7. Rejected malformed /execute syntax without creating a new run. Closed the TUI and fixture; the TUI exited 0 with alternate-screen restoration.
8. Applied one presentation-only code patch: independent terminal title, neutral Base Harness labels for legacy primary roles, and execution lifecycle labels derived from Host phase.
9. Ran targeted TUI tests and typecheck, then reopened the same saved session in a fresh read-only Host to inspect the changed title and labels.

### Changed files

- `runtime/packages/tui/src/app.tsx`
- `runtime/packages/tui/src/component/prompt/index.tsx`
- `runtime/packages/tui/src/routes/session/index.tsx`
- `runtime/packages/tui/src/feature-plugins/verification.tsx`
- `runtime/packages/tui/src/harness/status-presentation.ts`
- `runtime/packages/tui/test/harness-status-presentation.test.ts`
- `runtime/packages/tui/src/harness/identity-presentation.ts`
- `runtime/packages/tui/test/harness-identity-presentation.test.ts`

No execution authority, domain policy, provider/model selection, reasoning capability mapping, verifier policy, Evidence policy, or Ready gate was changed. No extra model call or meta-review layer was added.

## Result

| Item | Evidence and result |
| --- | --- |
| Interrupted planning recovery | Native TUI discard observed; no model call for discard |
| Plan-only mutation boundary | Both target files absent and Ready ineligible at plan_ready |
| Invalid plan ID | Explicit Host 400 error; same run/revision; no target files |
| Explicit execution | New execution run linked to the reviewed planning run and plan revision |
| Independent completion | Two completed WorkUnits, four Evidence references, zero repairs, real Python root Ready |
| Reasoning label propagation | Fixture-native high reached new TUI planning, both review phases, both workers, and root integration |
| Native TUI exit | Both the execution TUI and later read-only TUI exited 0 |
| Presentation | Native terminal title and primary labels now display Base Harness |
| TUI typecheck | Exit 0 |
| Targeted TUI tests | 77 passed, 1 failed, 341 assertions across six files |
| Entire repository / real providers | Not established by this phase |

The new failing test expects `Build-tools`, while the existing `Locale.titlecase` formatter returns `Build-Tools`. The production helper intentionally retains that existing formatter. The incorrect test expectation has been disclosed and left unchanged pending the user's decision; there was no second corrective production patch.

The execution lifecycle helper passes its targeted tests. Its Ready rendering was not re-established in the post-patch live probe because that probe exposed a separate Host restart gap.

### New blocking usability finding: completed-session restart continuity

Before shutdown, session `ses_f83167b5bffefeh7eAfPKMfUN3` had execution run `run-1bf74fd5-bbbe-4dd7-b3b9-dce73ca1f7c6`, Ready, four Evidence references, and develop + hackathon.

After reopening the same workspace/state and session, both the cold GET and the GET after TUI attachment returned:
- phase: inactive
- runId: empty
- evidenceCount: 0
- domain: develop
- skills: empty

The TUI loaded the existing conversation and selected model/variant, and both result files still existed. Its harness panel nevertheless displayed INACTIVE and no previous verification summary. Thus this is not merely an old TUI label: the Host API view itself loses the completed-run and skill context.

The current cached KernelHost source explains a matching gap: readStatus at line 232 consults ReviewedPlanStore.findPending at line 238; explicit execution consumes the reviewed plan at line 601. That pending-plan recovery path cannot by itself hydrate the last completed execution. This is a source-level explanation consistent with the observed behavior, not a completed audit of every persisted runtime index.

The read-only probe supervisor had non-TTY stdin, so interactive stop input was unavailable. Its bounded 120-second watchdog stopped the owned Host (exit 143) and ended the helper with exit 1. This probe is diagnostic evidence, not a passing lifecycle gate.

## Evidence

- Machine-readable diagnostic record: `docs/evidence/TUI_EXECUTION_REVALIDATION_AND_RESTART_GAP_2026-09-08.json`.
- Successful execution fixture: `.tools/validation/restoration-phase38-tui-recovery.result.json`.
- Failed earlier interactive attempt: `.tools/validation/restoration-phase37-tui-recovery.result.json`.
- Targeted test/typecheck output: `.tools/validation/restoration-phase38-tui-presentation-gates.log`.
- Real verifier artifact: `C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-MBpRue/state/base-harness/runs/f2162b024b14a239-3be89287/artifacts/51/513be75359128f1295a08f3b293ce0c4623c94ffcd84f55b7ee9b3f9776409dd.json`.
- Plan: `9c9749ac-0f7c-4ea9-a311-4ff2f6d9b7f7@1`.
- Planning run: `run-270cf1a5-21fd-4532-ba23-7193de122cf7`.
- Execution run: `run-1bf74fd5-bbbe-4dd7-b3b9-dce73ca1f7c6`.

Raw native PTY captures and before/after Host snapshots are retained in the JSON diagnostic record. PTY chunks are not GUI screenshots or a fully reconstructed terminal framebuffer.

## Requirement-oriented scope check

| Requirement group | Current evidence classification |
| --- | --- |
| Common Host controls across headless and TUI | Directly exercised for this recovery/plan/execute scenario; universal event parity remains unproved |
| Independent verifier and root-only completion | Real artifact inspected for these exact two file predicates |
| Reviewed plan revision execution | Exact ID acceptance and wrong-ID rejection directly exercised |
| Interrupted unexecuted plan recovery | Directly exercised |
| Last completed run and domain/skill recovery | Contradicted by the fresh Host/TUI probe |
| Broad complex-plan, queue, conflict, and repair reliability | Too narrow a fixture to conclude; not achieved by this report |
| Independent UI identity | Main terminal title and primary actor badges fixed and directly observed; no repository-wide branding claim |
| Model/OAuth/MCP usability | Local model and local MCP exercised; live provider login and remote MCP not established |
| Isolation, packaging, cross-platform, full regression promotion | Not newly established |
| Task performance/cost | Local HTTP timing and request traces only; no production LLM benchmark |

## Next implementation direction

1. Correct the new capitalization assertion only if the user approves; preserve the established formatter.
2. Hydrate a read-only last-run summary through the Host from validated, workspace-bound persisted state rather than reconstructing it from TUI message text.
3. Persist and restore domain/skill/planning preference independently of whether a reviewed plan is pending or already consumed.
4. Keep historical Ready separate from permission to mutate or execute; restoring a summary must not spawn workers, call models, create verifier attestations, or allow consumed-plan replay.
5. Add actual Host-restart fixtures for Ready, blocked, interrupted, direct runs, and domain/skill changes, including unchanged-file and changed-file cases.
6. Audit tool-schema advertisement against worker execution permissions; the local trace advertises bash/webfetch/planning tools to workers, which is not by itself proof of an execution-boundary bypass.

## Residual Risk

- The completed-session restart gap is unresolved, and one new display-only test remains failing.
- Existing same-model review common-mode errors are unchanged.
- A local scripted model does not establish real-provider task competence, latency, cost, or OAuth success.
- No new full-suite, Linux/WSL isolation, or independent distribution proof was produced.
- This phase used no Git commands, made no commit or push, and did not touch net_monitor.py.
