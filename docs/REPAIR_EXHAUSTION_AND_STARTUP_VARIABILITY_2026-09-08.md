# Repair Exhaustion and Startup Variability

Date: 2026-09-08
Status: Three-WorkUnit exhaustion fixture passed with explicit pure mode. Two default-path startup attempts failed. General startup reliability remains unresolved.

## Situation

One successful local repair does not prove that repeated failure stops after its budget, or that an exhausted worker allows queued independent work to continue. The next diagnostic therefore needed a persistently incorrect candidate and an independent WorkUnit that could not start immediately.

## Reason

The intended policy permits an initial implementation attempt and two automatic repairs with the same fingerprint. Exhaustion should stop that scope, not discard successful independent output or restart the whole plan. A required exhausted criterion must prevent root Ready.

A separate startup problem appeared before this scenario could run. It must remain visible rather than being erased by a later successful configuration.

## Action

Extended only:
- runtime/script/fixtures/local-runtime.ts
- runtime/script/verify-provider-public-boundary.mjs

BASE_HARNESS_FIXTURE_EXHAUST_WORKER=1 creates three required, independent file WorkUnits. Unit-0 always returns incorrect content. Unit-1's first write response waits at a test-only promise barrier until unit-2 reaches the provider, keeping a second slot occupied. The diagnostic's existing overall deadline bounds a scheduler deadlock; fixture shutdown releases the barrier.

The diagnostic checks three same-session writes for unit-0, two automatic repairs, a single fingerprint, persisted rejection outcomes, absence of a child attestation for the exhausted scope, no stored root Ready, retained correct outputs for units 1 and 2, and no contract/WorkGraph resubmission.

No production runtime, verifier, repair policy or default configuration was changed. The pending phase45 freshness-test correction was not applied.

## Result

| Run | Result |
| --- | --- |
| Original three-worker fixture, default inherited mode | Host health deadline failed after 30.26 s |
| One unchanged repeat | Host health deadline failed after 30.07 s |
| Isolated empty-config pure CLI help | Exit 0 after 14.48 s |
| Isolated empty-config pure Host | Healthy within 21.61 s |
| Three-worker fixture with explicit BASE_HARNESS_PURE=1 | Diagnostic passed; actual task correctly exited 1 |

Both default-path failures occurred before any model request or worker execution. Their Host stdout and stderr were empty. The diagnostic terminated the known Host processes after their readiness deadlines; these are startup failures, not evidence of repair-exhaustion failure.

The empty-config probes used a separate PowerShell process launcher and different configuration. They demonstrate that the entrypoint/server can start, not which variable caused the earlier failures.

The original three-worker fixture was then run with explicit pure mode. Its Host became healthy in about 10.15 s, provider listing took 13.81 s and the client took 38.22 s. These are single observations, not benchmark estimates.

In that completed negative-path test:
- Unit-0 remained in its original child session for three writes: initial attempt plus exactly two repairs.
- All three candidates had incorrect content. At both pre-repair observations the base target was absent, and it remained absent at the end.
- Persisted rejections had one fingerprint and outcomes repair, repair, repair_exhausted with rejection counts 1, 2 and 3.
- Unit-0 ended repair_exhausted with repairCount=2.
- Unit-2's first provider request occurred after the persisted exhaustion rejection. Its start released the test barrier holding unit-1.
- Units 1 and 2 each wrote once, completed without repair and retained correct files.
- No root integration model request or full replanning occurred.
- Root phase/outcome was blocked, failureKind was implementation_error and readyEligible was false.
- No root Ready artifact or scope attestation for unit-0 was stored.

The fixture supervisor returned 0 because the expected failure semantics passed. The actual headless task returned 1 because a required output remained unresolved. These exit codes must not be conflated.

## Evidence

Default-path failure records:
- .tools/validation/restoration-phase46-repair-exhaustion.result.json
- .tools/validation/restoration-phase46-repair-exhaustion-repeat.result.json

Separate startup probes:
- .tools/validation/restoration-phase46-isolated-help.result.json
- .tools/validation/restoration-phase46-isolated-serve.result.json

Conditional functional proof:
- .tools/validation/restoration-phase46-repair-exhaustion-pure.result.json
- Session: ses_f813e8516ffeJLTk2X8eiNuxy3
- Run: run-b5a248f5-50c9-4229-a1fa-23435c1c4c14
- Exhausted scope: ses_f813e3913ffeURNW6dguE7p0aB
- Final rejection: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-gcIkDe/state/base-harness/runs/8310ca1c1c170591-1e5cc98a/artifacts/dd/dd3d4a40395f491ec5f2288d289d85bfcfb405f17a8321da1c9c190427b9e002.json

Companion record:
- docs/evidence/REPAIR_EXHAUSTION_AND_STARTUP_VARIABILITY_2026-09-08.json

All controlled top-level process handles reached terminal state. Hosts were intentionally stopped by their diagnostic supervisors. No claim is made about a separate descendant-process sweep.

## Reproduction of the Passing Configuration

From the repository root with existing pinned runtimes:

```powershell
$env:BASE_HARNESS_PYTHON = Join-Path $PWD '.tools/verifier/Scripts/python.exe'
$env:BASE_HARNESS_DISABLE_MODELS_FETCH = 'true'
$env:BASE_HARNESS_PURE = '1'
$env:BASE_HARNESS_FIXTURE_FAIL_INTEGRATION = '0'
$env:BASE_HARNESS_FIXTURE_REPAIR_WORKER = '0'
$env:BASE_HARNESS_FIXTURE_EXHAUST_WORKER = '1'
$env:BASE_HARNESS_VALIDATION_TAG = 'repair-exhaustion-pure-local'
& ./.tools/bun-1.3.14/bun.exe run runtime/script/verify-provider-public-boundary.mjs
```

Choose a unique validation tag. These are diagnostic environment options, not a recommendation to disable production plugin features globally. The test invocations did not persist user environment settings.

## Residual Risk and Next Work

Default-path startup failed twice; it is not repaired. A later pure-mode pass suggests a useful comparison point but does not prove an external plugin is the cause. Execution order, cold initialization and environmental variability were not controlled well enough for causal attribution.

Source inspection shows the entrypoint imports the command graph before parsing CLI arguments. That is a potential source of startup cost, not a measured root cause. The next useful step is bounded, secret-free startup-stage instrumentation and a controlled comparison of otherwise identical Host launches.

The provider is scripted, the test barrier deliberately shapes scheduling, and the same implementation agent authored the diagnostic. This is not an independent assessment or real-model reliability. It covers one exhaustion path with simple files, not arbitrary DAGs, long sessions, cancellation, OAuth or multiple operating systems.

The file absence checks are discrete observations, not continuous filesystem surveillance. No full regression suite or typecheck was run in this diagnostic-only phase. The previous Python regression gate remains 64 passed / 1 failed due to the pending new-test freshness setup correction. Earlier phase38 and phase40 issues also remain unresolved.

No Git operations, commit or push occurred. net_monitor.py was untouched. This report and its JSON are engineering records, not Harness Evidence/Ready, and do not supersede failed runs.
