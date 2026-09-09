# Cold Plan Status and Revision Intent

Date: 2026-09-07
Status: Partial. Local restart/revision/execute passes; attached revision execution needs a follow-up.

## Situation

The previous audit demonstrated that a pending, signed reviewed plan resolved
successfully after Host restart, but the harness status endpoint returned
inactive/idle without its plan, contract or skills.

KernelHost also recorded revision-only intent in openRun(), but proposeContract()
could select direct execution for an atomic contract before reaching the
WorkGraph guard. Headless completion handling relied on --plan rather than the
Host's pending planning intent.

The earlier audit did not demonstrate an actual unauthorized file mutation.
This change addresses the source-level gap and adds explicit mutation-denial
regressions instead of claiming that an unobserved escape occurred.

## Reason

Display hydration, planning revision and execution are different operations.
A status request must not reconstruct an opaque execution capability, launch
workers, start verification or create Ready. An ordinary message in plan_ready
must revise the plan even when the revised contract is otherwise eligible for
direct execution. Only the typed execute request may initiate execution.

## Action

- Added optional pending-plan lookup that distinguishes an absent session pointer from a broken referenced recipe.
- Made plan-store read paths non-creating; canonical/HMAC checks remain mandatory.
- Added coalesced KernelHost.readStatus() for cold, read-only plan hydration.
- Shared structural reviewed-plan validation with the execution restoration path.
- Connected Host GET harness, ordinary prompts and cold controls to hydration.
- Exposed a typed Host planOnly boolean and used it in prompt and CLI completion handling.
- Kept an atomic revision in planned state before WorkGraph submission.
- Cleared the consumed pending record on revision and cleared revision intent on discard.
- Kept execution-time basis, selection and policy checks separate from display restoration.
- Added eight KernelHost regressions and extended the local fixture with revision and cross-directory scenarios.
- Scoped deterministic fixture tool history to its latest user turn; this is test routing, not production natural-language policy.
- Did not alter Python verifier protocol v4, Candidate attestation, Overlay commit protection or root-only Ready.

## Result

| Gate | Result |
| --- | --- |
| KernelHost tests | 45 passed, 0 failed; 186 expectations |
| Routing and headless helper tests | 28 passed, 0 failed; 67 expectations |
| Total targeted unit tests | 73 passed, 0 failed |
| KernelHost, Host, TUI typechecks | Passed |
| Cold Host pending-plan GET | Passed; plan/contract/skills restored, no model completion call |
| Cold ordinary-message revision without --plan | Passed; revision 1 to 2, no output files or Ready |
| Local standalone execution from another directory without --dir | Passed; both worker files and real verifier Ready |
| Local revised-plan execution with Provider failure | Passed; blocked, model_provider_error, no Ready |
| Attached ordinary-message revision | Returned plan_ready revision 2, no workers or output files |
| Attached revision-to-execute fixture | Failed on a newly added run-ID assertion before execute was reached |

### Local lifecycle evidence

- Session: ses_f84153c7dffeR31CFmv6Na8wKG
- Plan: 2cc84870-37b5-438b-9d16-9862abfd3c7d
- Original planning run: run-c05950c1-b365-4c71-a96d-748097ad9bb4
- Revised planning run: run-033ca1b5-7b06-40e2-a954-419c46fe93e6
- Execution run: run-dab5c8a7-d8e0-4a3a-8dc9-25137435d161
- The cold snapshot had phase=plan_ready, planningState=plan_ready, planOnly=true, verificationState=inactive and readyEligible=false.
- Both output files remained absent until the explicit execute client.
- The execution linked plan revision 2 and its reviewed contract hash.
- Provider-native max was retained throughout the scripted pipeline.
- Contract and plan reviews ran for each planning revision; GET and execute did not add reviews.
- Ready artifact: C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-0QmdPn\state\base-harness\runs\6c214a91fd2eb67f-66436ee9\artifacts\36\36c071058c7990f83e4d993c0cd7b8281b2dad919b2c75d2cf661e2824680dca.json

### Provider failure evidence

- Session: ses_f84118ba5ffeFi8UUR0chmCOiD
- Revised planning run: run-7b63fb4a-6daf-4355-aecc-5dd25e68e660
- Execution run: run-859d7d57-91e7-42a7-9db4-4af0f77d4a22
- Execute exited 1 with blocked/model_provider_error and readyEligible=false.
- Previously verified worker commits remained, and the fixture found no Ready attestation.

### Attached fixture limitation

The new test expected every plan revision to create a different run ID.
A live attached Host currently reuses its existing planning run:

- Original revision: 1
- Revised revision: 2
- Shared run: run-79c55abc-301e-4c20-8b7e-a14427fcb94f
- Both CLI clients exited zero with planOnly=true and readyEligible=false.
- Model worker/integration requests: 0
- Output files present: [false,false]

The assertion failure is not evidence of unintended execution. The original
planning contract requires a revision increase and explicit execute, not
necessarily a fresh run for each revision. However, simply removing the
assertion would also be premature: Coordinator.openRun() currently preserves an
existing run's goal/source/policy and updates its context. A follow-up should
exercise changed requirements, not only repeat the same fixture goal, and
establish how revised source provenance and policies reach execution.

No second corrective source patch was applied. The failing attached fixture
remains failed, and its standalone cross-directory execution was not reached.
The local negative case was then run independently and passed.

## Evidence

- .tools/validation/restoration-phase25-gates.json
- .tools/validation/restoration-phase25-kernel-host-tests.log
- .tools/validation/restoration-phase25-kernel-host-typecheck.log
- .tools/validation/restoration-phase25-host-tests.log
- .tools/validation/restoration-phase25-host-typecheck.log
- .tools/validation/restoration-phase25-tui-typecheck.log
- .tools/validation/restoration-phase25-local-revision-cross-directory.log
- .tools/validation/real-headless-plan-local-standalone-revision-cross-directory.result.json
- .tools/validation/restoration-phase25-attached-revision-cross-directory.log
- .tools/validation/real-headless-plan-attach-standalone-revision-cross-directory.result.json
- .tools/validation/restoration-phase25-local-revision-provider-failure.log
- .tools/validation/real-headless-plan-local-failure-standalone-revision.result.json
- .tools/validation/restoration-phase25-handoff.json

## Residual Risk

- An interrupted revision fails closed with PLAN_REVISION_INTERRUPTED. Same-session recovery or discard of that interrupted revision is not implemented; use a new session rather than deleting authority records.
- Displaying a saved plan does not certify current basis freshness or Provider availability; execute still checks them independently.
- The attached run-lifecycle and revised goal/source propagation need explicit follow-up before claiming full local/attach equivalence.
- These are deterministic local model/MCP tests with the real Python verifier, not live OAuth/subscription certification.
- TUI typechecking is not a new interactive or visual TUI certification.
- The complete repository suite, all platforms and sandbox guarantees were not re-certified.
- The existing same-OS-account HMAC threat limitation remains.
- No git commands, commits or push were performed. net_monitor.py was not edited.

