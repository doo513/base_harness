# Native TUI Model Selection and Plan Execution Follow-up (2026-09-08)

## Situation
The auth-store guard had passed source-mode Host initialization and repair diagnostics, but those checks did not operate the actual TUI. Its test-only TS2352 remains unresolved.

## Reason
The displayed model, reasoning effort, planning controls and completion state must agree with actual Host requests and independently checked artifacts. An HTTP-only fixture cannot establish the interactive wiring.

## Action
- Launched the current source TUI in a native Windows PTY against an isolated actual Host.
- Used a local synthetic model/MCP fixture and the actual Python verifier, without paid model calls.
- Deliberately interrupted a plan revision, restarted the Host, and attached the TUI to that recovered session.
- Operated the model selection dialog, selected Fixture reasoner, and changed high to the provider-advertised max via the TUI.
- Used /plan discard, /plan, an ordinary request, /harness, an invalid /execute ID, and then /execute with the reviewed ID.
- Recorded selected terminal frames, Host snapshots, model request metadata and final verifier checks.
- Made no production or test source changes in this follow-up.

## Result
- The model selector opened with both fixture models available.
- Recovery required explicit plan discard; discard made no model call or Ready artifact.
- /plan alone left planningState idle, planOnly true, Ready unavailable, and both target files absent.
- The ordinary request produced a new reviewed plan without starting workers or creating target files.
- The overlay displayed PLAN_READY and explicitly said /execute was required and Ready had not been issued.
- /execute missing-plan produced PLAN_ID_MISMATCH / HTTP 400, preserving the reviewed plan and absent targets.
- The valid /execute opened a different execution run and completed two WorkUnits.
- Both exact target contents and a real verifier Ready covering both required claims and criteria were checked by the fixture.
- The TUI displayed READY (adaptive), two completed workers, and Planning idle.
- All 11 model requests after discard used Fixture reasoner and exact max, including contract review, plan review, workers and integration.
- Worker-visible tools were edit, glob, grep, read and write.
- TUI exit: 0. Fixture exit: 0. Both Hosts exited 143 after intentional stop.
- Terminal alternate-screen and bracketed-paste restoration sequences were observed.

Planning run: run-3d13b2d4-ce48-4bad-862d-21c96c170417
Execution run: run-29d2b59e-6cff-4494-b8c9-8584820aae80
Reviewed plan: c84cb471-c34f-4db1-aa6f-8a0cf9793ed8
Root session: ses_f80cc76ccffeqEJRLuGoNlq2Ip

## Evidence
- .tools/validation/tui-post-auth-1788840461544.result.json contains the fixture outcome and artifacts.
- The companion docs/evidence JSON includes selected PTY frames and public Host snapshots.
- The Ready artifact path is recorded in the companion JSON; the engineering report itself grants no Harness Evidence or Ready authority.

Host startup observations were 11.158 s and 6.417 s. Empty-status median was 15.87 ms and pending-plan median was 39.61 ms. These are different paths and single-run observations, not a comparative speed guarantee.

## Residual Risk
- The new Auth test mock still fails Host typechecking with TS2352. This diagnostic does not clear that gate.
- Scripted local model behavior cannot establish real OAuth/provider availability, independent reasoning quality or arbitrary-project reliability.
- The terminal test covers the observed Windows PTY size. It is not a desktop screenshot review, complete CJK/resize audit, or Linux/WSL test.
- Startup delay and previously recorded unrelated failures remain open.
- Git and net_monitor.py were untouched. No commit, push or release promotion occurred.
