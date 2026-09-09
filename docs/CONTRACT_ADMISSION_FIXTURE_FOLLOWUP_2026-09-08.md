# Contract Admission Fixture Follow-up

## Situation

Two failures in the full Host baseline came from contract-tool tests written for synchronous registration without the now-required interpretation block. An async rejection was left unobserved and appeared during the next test.

## Reason

A submitted proposal is not execution permission. Runtime acceptance, Kernel planning state, and typed revalidation still govern admission. Tests must await registration and exercise that policy rather than remove those guards.

## Action

- Added required InterpretationProposal to the adapter's HarnessContractProposal TypeScript interface, matching the existing public tool schema.
- Replaced outdated fixtures with asynchronous registration tests.
- Used an isolated real KernelHost and deterministic runtime acceptance stub. Bound Kernel methods are redirected through scoped spies and restored in finally; no module mock or replacement permission policy is installed.
- Added checks for pending acceptance, invalid Claim-Criterion binding, missing interpretation, runtime rejection, plan-only acceptance, typed revalidation after prior acceptance, and consequential ambiguity.
- Production admission and verifier behavior were not loosened.

## Result

- Corrected the two fixture hostOperation values from write to mutate, matching the existing Kernel enum. Tool IDs and permission policy were unchanged.
- Latest Bun 1.3.14 check: 14 passed, 0 failed, 72 assertions across 3 files, 6.78 seconds.
- Latest Host typecheck: exit code 0.
- This focused gate now passes. No full Host-suite success is claimed.
- Previous attempt retained for audit: execution tests passed, but typecheck exited 2 because this work introduced two invalid enum values. That failure was disclosed before correction.

## Evidence

- Latest log: .tools/validation/contract-admission-enum-1788851685046.log.
- Previous failed-attempt log: .tools/validation/contract-admission-fixture-1788851530099.log.
- Latest terminal session 79452: CONTRACT_ADMISSION_GATE tests=0 typecheck=0.
- Previous terminal session 53626: CONTRACT_ADMISSION_GATE tests=0 typecheck=2.
- Previous type errors at test/tool/harness-contract.test.ts lines 85 and 100 (TS2345) are resolved by the current typecheck.
- ToolOperation is defined at runtime/packages/kernel/src/index.ts:189; operationForTool maps write/edit/apply_patch to mutate.
- Companion: CONTRACT_ADMISSION_FIXTURE_DIAGNOSTICS_2026-09-08.json.
- Diagnostics are not Harness Evidence, Ready attestations, or independent user validation.

## Residual Risk

- The enum correction passed the focused gate; complete-suite and live-verifier acceptance remain separate requirements.
- The runtime stub is not a real Python verifier or real-account integration check.
- Scoped prototype spies assume serial execution; concurrent execution of these fixtures is not established.
- Other baseline prompt, snapshot, Windows symlink, schema snapshot, and removed plan-agent fixture failures remain unaddressed.
- No complete Host-suite pass or user stability result is claimed.
- No Git operation was performed; net_monitor.py was untouched.
