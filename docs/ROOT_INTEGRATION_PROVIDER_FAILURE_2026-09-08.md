# Root Integration Provider Failure Diagnostic

Date: 2026-09-08
Status: Scoped negative-path fixture passed; user reliability remains unproven.

## Situation

Successful local execution does not establish correct behavior when a provider fails after workers have already produced outputs. This boundary must distinguish an infrastructure failure from an implementation defect and must not turn completed child work into root Ready.

## Reason

An integration provider error must not start code repair or an unnecessary new plan. Already committed worker output must remain available, while the root completion gate stays closed. The earlier successful fixture cannot prove these properties.

## Action

Extended runtime/script/verify-provider-public-boundary.mjs with BASE_HARNESS_FIXTURE_FAIL_INTEGRATION=1. This flag enables the existing planned local fixture and its existing integration-failure response.

The local provider returns HTTP 400 with invalid_request_error and fixture_integration_failure only at root integration. This is a deterministic test provider, not an external account. No production policy or runtime code changed in this phase.

The diagnostic now checks the non-success client exit, typed failure kind, blocked root status, zero repair counts, one contract submission, one WorkGraph submission and one root integration request. It compares both retained output files with expected content, checks persisted session history, and inspects the isolated run storage for a root Ready attestation.

The storage inspection is bounded to 512 entries and does not follow symbolic-link entries. Its scope is the fresh fixture state, not arbitrary user storage.

## Result

- The diagnostic supervisor exited 0 because the expected failure behavior was observed.
- The actual headless task exited 1. It did not succeed.
- Root phase and outcome were blocked; failureKind was model_provider_error and readyEligible was false.
- Both workers remained completed with repairCount=0. Root repairCount was also 0.
- Both output files retained their exact expected content.
- One root integration request was made; one contract and one WorkGraph submission were recorded.
- The bounded scan examined 42 entries and 17 JSON files, all 17 belonging to the current run. It found no persisted root Ready attestation.
- Persisted session history recorded the same blocked run and revalidated=false.
- Worker catalogs retained permitted editors and did not advertise forbidden tools. Public provider metadata checks also remained satisfied.
- The Host was intentionally terminated by the diagnostic and exited 143. The diagnostic process reached terminal exit 0.

## Evidence

- Session: ses_f815ea6c7ffehCSbjUMgFXQFhA
- Run: run-fb38775a-49da-4bdf-9923-7e3b4940d5a5
- Gate output: .tools/validation/restoration-phase43-integration-provider-failure.log
- Complete diagnostic result: .tools/validation/restoration-phase43-integration-provider-failure.result.json
- Companion record: docs/evidence/ROOT_INTEGRATION_PROVIDER_FAILURE_2026-09-08.json
- Reusable diagnostic: runtime/script/verify-provider-public-boundary.mjs

Reproduction from the repository root in PowerShell, using the existing pinned runtime:

```powershell
$env:BASE_HARNESS_PYTHON = Join-Path $PWD '.tools/verifier/Scripts/python.exe'
$env:BASE_HARNESS_DISABLE_MODELS_FETCH = 'true'
$env:BASE_HARNESS_FIXTURE_FAIL_INTEGRATION = '1'
$env:BASE_HARNESS_VALIDATION_TAG = 'integration-provider-failure-local'
& ./.tools/bun-1.3.14/bun.exe run runtime/script/verify-provider-public-boundary.mjs
```

Use a unique validation tag to preserve earlier diagnostic logs. The failure flag applies to the diagnostic only. Remove it from the shell environment when running the success scenario.

## Residual Risk

This is an implementation-agent-authored deterministic integration check. It is not independent user validation or a real-provider reliability estimate. The Python verifier and real Host processes provide runtime evidence but do not eliminate common design/test assumptions.

No actual rejected implementation candidate or successful local repair was exercised. Zero repair counts show that this provider error avoided code repair, not that repair works for implementation errors.

This case covers one non-retryable HTTP 400 after worker completion. It does not cover OAuth expiration, rate limiting/backoff, transport disconnects, streaming corruption, cancellation, long sessions, manual re-verification, Host restart, other operating systems, or real model behavior.

The final-state and artifact checks do not constitute a complete event-stream audit. Absence of a stored root attestation in the fresh inspected run is narrower than proving every possible observer could never see a transient incorrect event.

The success branch was not rerun after this diagnostic extension. Earlier phase41/42 success results remain historical scoped evidence. No full regression suite or typecheck was run in this phase because only the diagnostic script was extended.

Existing phase38 titlecase-test and phase40 short-readiness diagnostic issues remain unchanged. No Git operations, commits or push were performed; net_monitor.py was not touched.

Next substantive work remains implementation-error rejection and bounded local repair, followed by real-provider and independently evaluated user tasks. This report is an engineering record, not Harness Evidence or Ready.
