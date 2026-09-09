# Session history restoration implementation

Date: 2026-09-08
Workspace: C:\Users\doo33\Downloads\base_harness
Status: Implemented; selected regression gates and a real selection-only restart probe passed. Full runtime restoration is not yet proven.

## Situation

The prior native Windows run reached Python-verifier Ready, but after Host restart the same session returned an inactive harness view and lost its hackathon choice. Result files and verifier artifacts remained on disk. Existing coordinator telemetry did not contain enough metadata to reconstruct the full presentation.

## Reason

Kernel session choices existed in memory. Cold status lookup restored pending reviewed plans, not completed-run history. An asynchronous presentation subscriber was not a reliable place to persist the final state before the process ended.

History must not become execution authority: an old Ready cannot prove the current workspace, and a saved summary must not resume a worker, open a verifier, or authorize a consumed plan.

## Action

- Added a separate Host-private SessionStateStore with bounded, signed, atomically replaced session snapshots outside the workspace.
- Persisted validated domain, skill, plan preference and execution selection metadata. Permission-bearing selection cannot be silently changed by redaction.
- Whitelisted and bounded the previous run summary. Full contracts, model contexts, credentials, candidate attestations and execution capabilities are not restored from it.
- Kept historical metadata nested under history. Active phase, run ID, evidence collections and Ready eligibility remain inactive after cold lookup.
- Marked nonterminal historical phases interrupted and all history read-only and not revalidated.
- Preserved the existing reviewed-plan store, signature, consumption and explicit execute path.
- Added an awaited Coordinator checkpoint before status publication and latched durable-storage failures as Host failures, not implementation repair.
- Serialized session controls and passed the HTTP workspace into selection persistence.
- Added historical TUI presentation without changing verification authority or the sidecar protocol.

## Result

### Selected tests and types

- KernelHost history, restoration and reviewed-plan recovery: 50 pass, 0 fail.
- Coordinator checkpoint publication: 3 pass, 0 fail.
- TUI history/lifecycle helpers: 28 pass, 0 fail.
- Total: 81 pass, 0 fail across six selected files.
- KernelHost, Coordinator, Host and TUI typechecks: exit 0.

These are bounded regression results, not a full-suite or independent reliability claim. The checkpoint Ready-publication test deliberately uses a synthetic internal snapshot; it is not a real verifier acceptance and is not presented as one.

### Real Host restart probe

A real Windows Host received skill.set(hackathon) and planning.plan_once through HTTP. After stopping the Host and starting it again, the same session returned:

- domain: develop
- skills: [hackathon]
- planningPreference: plan_once
- planningState: idle
- phase: inactive
- runId: empty
- readyEligible: false

This confirms real HTTP selection persistence without creating a new run or granting Ready. It does not prove completed-run history presentation in native TUI.

### Incomplete full fixture

The planned headless execution/restart fixture stopped at its Host readiness deadline, before planning or model work. Host stdout showed a listening server and stderr was empty. A separate probe returned health HTTP 200 and provider HTTP 200; the first provider request took about 7.5 seconds, while the failed fixture allowed only 2 seconds per provider readiness request.

Consequently the full fixture remains failed, and that failure is not evidence that the executable cannot start. Its timeout/diagnostic design needs attention before the full sequence can be accepted.

## Evidence

- `.tools/validation/restoration-phase40-session-history-gates.log`
- `.tools/validation/restoration-phase40-host-history.result.json`
- `.tools/validation/restoration-phase40-host-history-host-1.stdout.log`
- `.tools/validation/restoration-phase40-host-history-host-1.stderr.log`
- `docs/evidence/SESSION_HISTORY_RESTORATION_IMPLEMENTATION_2026-09-08.json`

The evidence JSON records the successful selection probe separately from the failed full fixture. These documents are diagnostics, not Harness Evidence or Ready artifacts.

## Residual Risk

- Real completed-run restoration, native TUI rendering of the history panel, and full regression coverage remain unproven for this patch.
- The prior capitalization expectation failure (Build-tools versus Build-Tools) remains unchanged and outside the selected test run.
- GET /provider returned a fake fixture API key in options. This is an observed response-minimization concern, not proof that a real user key was leaked or an unauthorized client accessed it.
- Legacy telemetry is preserved but is not retroactively promoted to signed history; missing historical detail is not invented.
- Multiple independent Hosts are not coordinated by the in-process serialization queue. HMAC does not protect against an adversarial process with the same user's access to the signing key.
- Saved history may intentionally remain historical Ready after workspace files change; revalidated=false and inactive current authority are essential.
- Storage signing and checkpoint I/O may add latency. No representative performance or long-duration user-workload claim is made.
- External OAuth providers, real service-specific reasoning behavior, Windows/WSL/Linux sandbox boundaries and standalone distribution were not validated here.
- Owned probe terminal handles ended after intentional Ctrl+C. This is not a full descendant-process cleanup or graceful shutdown proof.
- No Git commit or push was made. net_monitor.py was not touched.

## Next work

1. Correct the readiness diagnostic with explicit approval, then repeat real plan/execute/completed-history restoration with the existing local provider and real verifier.
2. Inspect the native TUI history display on the completed fixture.
3. Audit provider response redaction and the advertised worker tool set against actual execution permissions.
4. Keep local deterministic gates separate from actual user/model reliability evaluation.
