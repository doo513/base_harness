# Standalone Plan Routing and Cold-State Audit

Date: 2026-09-07
Status: Standalone routing fixed and execution verified in fixtures. Cold pending-plan presentation remains incomplete.

## Situation

The standalone execute command reached the Host but plan lookup returned HTTP
500. Shared workspace routing interpreted the static harness segment in
/session/harness/plan/<planId> as a SessionID.

## Reason

Routing should infer a session only when the segment satisfies the existing
typed SessionID contract. Maintaining a growing list of English-looking path
exceptions would repeat the same failure for future static namespaces.
Endpoint parameter validation and authorization remain separate responsibilities.

## Action

- Replaced the throwing routing-hint constructor with a cached SessionID schema decoder.
- Return no session hint for non-session segments while preserving valid session routing.
- Added six regression cases for static plan/catalog paths and malformed session-like routes.
- Ran routing/HTTP middleware/headless helper tests and Host/TUI typechecks.
- Ran actual standalone CLI execution in local-restart, Provider-failure and attached scenarios.
- Probed an existing, unexecuted reviewed plan after starting a fresh Host.

## Result

| Gate | Result |
| --- | --- |
| Routing, HTTP workspace middleware and headless helper tests | 37 passed, 0 failed; 98 expectations |
| Host typecheck | Passed |
| TUI typecheck | Passed |
| Local plan-only followed by a new-process standalone execute | Passed; both workers completed and real Ready was produced |
| Local standalone execute with integration Provider failure | Passed; execute exited 1, blocked, no Ready |
| Attached standalone execute | Passed; both workers completed and real Ready was produced |
| Pending-plan lookup on a fresh Host | HTTP 200 |
| Pending-plan status presentation on a fresh Host | Incomplete: idle/inactive, no active plan, empty skills |

The real-flow fixtures supplied the workspace directory. These results are not
a separate certification of invocation from an arbitrary directory without
--dir. They retain checks for original contract linkage, fresh execution run,
provider-native max reasoning effort, hackathon selection, no repeated reviews,
both output files and actual verifier-backed Ready evidence.

### Local standalone success

- Planning run: `run-ce046607-2dd0-449f-a536-b39fe07a336c`
- Execution run: `run-4b923695-03f5-47c6-a1d9-df0be66f7f56`
- Execute exit code: 0.
- Ready artifact: `C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-T3vgXo\state\base-harness\runs\17f27e247e40cf30-ab42f081\artifacts\83\834c30fbe8801326883ad170f2d70d9969517fc7045a33bebaf621683db717c0.json`

### Local standalone integration failure

- Planning run: `run-fa352399-2f31-4ee5-8bdc-d0a49e4ca6b4`
- Execution run: `run-2f90273e-3f45-4f4e-b395-609f3b3c4492`
- Execute exit code: 1, without an observation timeout.
- Failure classification: model_provider_error.
- Verified worker commits remain, but the root is blocked and no Ready is issued.

### Attached standalone success

- Planning run: `run-c693164c-02fb-45a4-afd3-78314697c1c7`
- Execution run: `run-a7f3f3ff-01c6-48ba-ac5a-e14b9465c746`
- Execute exit code: 0.
- Ready artifact: `C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-6AKBSn\state\base-harness\runs\ae5a885b3547d27b-e442517b\artifacts\c6\c605b55c135ee06361f54301588aeaaae05540c14082a6de1057ab8fe5b8876e.json`

## Evidence

- `.tools/validation/restoration-phase24-gates.json`
- `.tools/validation/restoration-phase24-routing-tests.log`
- `.tools/validation/restoration-phase24-host-typecheck.log`
- `.tools/validation/restoration-phase24-tui-typecheck.log`
- `.tools/validation/restoration-phase24-local-standalone.log`
- `.tools/validation/restoration-phase24-local-standalone-failure.log`
- `.tools/validation/restoration-phase24-attached-standalone.log`
- `.tools/validation/restoration-phase24-pending-plan-preview.json`

## Remaining cold-state gap

The pending-plan probe used the previously unexecuted plan
`d3bd831f-b02e-4386-8ab1-f069419d1a51` in session `ses_f844dff57ffeMgA73O2sh1WsXc`.

The fresh Host returned HTTP 200 for the original session and plan descriptor,
but GET /session/<sessionId>/harness returned:

```json
{
  "phase": "inactive",
  "planningState": "idle",
  "planningPreference": "auto",
  "skills": [],
  "readyEligible": false
}
```

No activePlanId or plan steps were present. This is authoritative evidence of
missing cold-state presentation, not a visual TUI test. The plan has not
disappeared: explicit execution preparation can restore it, while a status
query cannot yet do so.

The initial preview probe referenced a fixture that had already executed. It
is not used as evidence of the pending-plan gap. The pending-plan evidence
above identifies a separate unexecuted fixture explicitly.

## Next implementation boundary

- Add read-only hydration of unexecuted, integrity-checked reviewed plans for Host status consumers.
- Do not create a verifier, dispatch workers or issue Ready merely by querying status.
- Preserve consumed/discarded/interrupted execution behavior; do not auto-resume work.
- Add a cold-restart negative test for an ordinary user message after plan_ready. It must revise the plan, not become implicit execution.
- Evaluate that ordinary-message boundary in addition to presentation; no live mutation violation is claimed by the read-only probe.
- Verify the updated Host status contract in TUI/headless and test standalone execution from another directory.

## Residual Risk

- The cold pending-plan presentation gap remains.
- Ordinary-message plan-only preservation across restart needs a dedicated regression.
- Tests use local deterministic model/MCP fixtures and the real Python verifier, not paid external models.
- No new interactive TUI, complete-suite or cross-platform certification is claimed.
- Existing same-OS-account signing-key and broader sandbox/platform limitations remain.
- No git commands, commits or push were performed. net_monitor.py was not edited.
