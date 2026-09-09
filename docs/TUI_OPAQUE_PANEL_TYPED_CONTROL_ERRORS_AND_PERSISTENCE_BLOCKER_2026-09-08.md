# TUI opaque panel, typed control errors, and persistence blocker

Date: 2026-09-08
Status: INCOMPLETE. Do not promote or describe this revision as fully verified.
Goal: Continue restoring a usable independent Base Harness without weakening verification authority.

## Situation

Phase32 left a transparent verification overlay, a generic control-error toast, and a next-request planning label that remained visible during active planning. Phase32 had a successful local TUI-to-verifier fixture. That earlier success is not evidence that the current revision passes.

A fresh pre-edit HTTP probe returned HTTP 500 with an UnknownError and a correlation reference rather than an actionable plan rejection. The opacity and planning-label problems were therefore not the only user-facing failure.

## Reason

- An overlay must erase transcript glyphs under both text and whitespace, including its scrolling viewport.
- The TUI should render authoritative planOnly and planningState fields rather than infer workflow policy from prose.
- Host control errors should expose explicitly recognized error codes, without publishing arbitrary exception messages, paths, stacks, or credentials.
- Unknown server failures must retain the existing generic error boundary.
- UI improvements are not a substitute for compilation gates or a successful end-to-end execution.

## Action

1. Extracted HarnessPanelFrame with an opaque theme-derived surface, fixed header/footer, bounded body, and vertical-only scrolling.
2. Added renderer tests that place a dense transcript underneath both short and long overlays at 80x24 and 40x12; tests inspect overlay whitespace before scrolling, after scrolling, and after returning to the top.
3. Added a typed presentation helper that distinguishes the next plan-only request, an active plan-only run, a reviewed plan, and interrupted-plan recovery.
4. Preserved typed slash dispatch and opaque explicit plan IDs.
5. Added a TUI response reader for top-level and nested Host errors, including exact code/kind, HTTP status, safe message, and correlation reference. It does not classify failures or authorize actions.
6. Mapped a bounded set of internal Error.code values to the existing InvalidRequestError HTTP contract. Message-only errors, actor-shaped JSON, and unknown codes are not reclassified.
7. Declared that error on the Host control endpoint and regenerated the V2 SDK using the official build script with Bun 1.3.14.
8. Ran targeted tests, typechecks, and a new native PTY TUI attachment to a real Host with local deterministic model/MCP responses and the real Python verifier available.

The manual source patch touched 11 files. SDK generation was an additional planned generated-output phase. No second manual source correction was made after failures were discovered.

## Result

### Functional improvements observed

- TUI runtime tests: 68 passed, 0 failed, 313 expectations.
- Host control tests: 5 passed, 0 failed, 11 expectations on serial rerun at the same 30-second timeout.
- An initial Host run had 5 passing cases and an unnamed cleanup-hook timeout. This initial failure remains part of the record; its cause was not established.
- SDK code generation and its TypeScript build exited 0.
- Actual TUI overlay opening, PageDown, and PageUp showed an opaque panel with fixed footer and no horizontal scrollbar.
- Typed /plan discard was observed by the fixture monitor without additional model calls or Ready creation.
- Before submitting a new goal, the Host reported planningPreference=plan_once, planningState=idle, planOnly=true, readyEligible=false, with both target files absent.
- The TUI displayed next: plan-only before the request, then planning: plan-only during contract_building.
- /execute missing-plan displayed PLAN_ID_MISMATCH and HTTP 400 with a useful Host explanation.
- A separate HTTP check confirmed the same error and preserved the plan/run IDs; target files were absent.

### Gates that did NOT pass

- TUI typecheck exited 2: two test assertions omit the explicit generic type for unwrapHarnessResponse.
- Host typecheck exited 2: the catchCause recovery callback needs an explicit union error return type; the inference failure also affects the route and test types.
- The new interactive scenario did NOT reach Ready.
- The Coordinator encountered EPERM while renaming its temporary orchestration snapshot to orchestration.json.
- The monitor captured this persistence failure before the wrong-ID and valid-ID execution attempts. It is not evidence that the wrong-ID request caused the blocked state.
- The reviewed plan metadata coexisted with Coordinator phase=blocked and failureKind=harness_error.
- The valid-ID execution attempt returned a generic HTTP 500 with a visible correlation reference, and execution did not produce workers or Ready.
- The after-edit fixture was deliberately stopped after recording the failed state. It exited 1 because the recovery/plan/execute completion assertion was unsatisfied. It was not restarted merely to obtain a passing result.

The TUI exited 0 and emitted terminal restoration sequences. Both fixture Hosts exited during controlled cleanup. No tracked process handle remains live.

## Evidence

### Source paths

- runtime/packages/tui/src/feature-plugins/verification.tsx
- runtime/packages/tui/src/harness/panel-frame.tsx
- runtime/packages/tui/src/harness/panel-presentation.ts
- runtime/packages/tui/src/harness/control-response.ts
- runtime/packages/tui/test/harness-panel-arguments.test.ts
- runtime/packages/tui/test/harness-panel-render.test.tsx
- runtime/packages/tui/test/harness-control-response.test.ts
- runtime/packages/base-harness/src/server/routes/instance/httpapi/handlers/session.ts
- runtime/packages/base-harness/src/server/routes/instance/httpapi/handlers/session-errors.ts
- runtime/packages/base-harness/src/server/routes/instance/httpapi/groups/session.ts
- runtime/packages/base-harness/test/server/harness-control-errors.test.ts

### Recorded outputs

- .tools/validation/restoration-phase33-gates.json
- .tools/validation/restoration-phase33-terminal.json
- .tools/validation/restoration-phase33-before-goal.json
- .tools/validation/restoration-phase33-wrong-plan-id.json
- .tools/validation/restoration-phase33-execute-failure-status.json
- .tools/validation/restoration-phase33-tui-presentation-after.result.json
- .tools/validation/restoration-phase33-tui-presentation-after.connection.json
- .tools/validation/restoration-phase33-handoff.json

The connection file contains stopped localhost URLs and must not be treated as a live handle.

Session: ses_f836c19feffela28Mpi5xXpUfg
Planning run: run-68c34d66-e628-4251-abf0-1f14c3466b96
Reviewed plan: 33e1effa-1554-437c-a595-d6714c9f2457, revision 1
Scratch root: C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-ZqEJfz

The failing state file was under:
state/base-harness/runs/run-68c34d66-e628-4251-abf0-1f14c3466b96/orchestration/orchestration.json

The .tmp source was orchestration.638daf5b-c8fd-4af9-9a9e-4ded09a99842.tmp.

Native PTY output is not a GUI screenshot. Some long streaming output chunks were truncated by the tool; the renderer assertions and selected command-response frames are the focused visual evidence.

## Residual Risk and Next Actions

1. Correct the two TypeScript generic issues before claiming compile readiness.
2. Investigate the actual orchestration snapshot writer and its Windows rename/concurrency behavior. EPERM is confirmed; a particular locking process, antivirus cause, or race has not been proven.
3. Propagate persistence failure coherently across Coordinator and Kernel: plan_ready metadata must not present an unconditional execute affordance while the run is blocked.
4. Preserve fail-closed Ready, candidate attestation, before hashes, and signed plan integrity. Do not repair this by deleting state, ignoring persistence errors, or granting Ready.
5. Retest the identical local TUI recovery/plan/execute flow after fixing the underlying problem, not only its display.
6. Confirm that explicit plan-domain/skill choices survive the first new TUI request. In this run the recovered state showed hackathon, but the new plan reported develop with an empty skills list; the cause was not investigated.
7. External provider/OAuth behavior, end-to-end cost improvement, and broader Windows isolation are not proven by the local fixture.
8. An expected code carried only in an untyped error message still remains a generic server error, intentionally. Broader typed producer coverage is a separate follow-up.

No git command, commit, or push was performed. net_monitor.py was not read or changed.

