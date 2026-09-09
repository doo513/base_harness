# Worker Local Repair and Evidence Lineage Observation

Date: 2026-09-08
Status: Local repair behavior passed the fixture; an evidence-state consistency concern remains open.

## Situation

Provider-failure handling was previously exercised, but a provider error is not an implementation defect. The next diagnostic needed to submit an incorrect worker candidate, allow independent rejection and observe a bounded local repair without restarting unrelated work.

## Reason

The accepted design requires candidate verification before commit, reuse of the original child session, retention of model/effort selection and no whole-plan restart for a local defect. A successful final file alone would not prove those intermediate properties.

## Action

Extended only the diagnostic sources:
- runtime/script/fixtures/local-runtime.ts
- runtime/script/verify-provider-public-boundary.mjs

BASE_HARNESS_FIXTURE_REPAIR_WORKER=1 enables a planned fixture where unit-0 first writes incorrect content and returns expected content on its next write. Unit-1 always returns expected content. The fixture recognizes its own WorkUnit markers in retained user-message history because a repair prompt does not repeat original instructions. This test-only response selection is not production natural-language policy.

The fixture samples the actual base target immediately before the repair response. The diagnostic also reads the actual child session's message API and checks that both writes belong to that same session. No production runtime or verifier logic changed.

## Result

- The real Host/headless/Python-verifier fixture completed with client exit 0.
- Unit-0 completed after one repair; unit-1 completed with no repair.
- Unit-0 had two completed write tool records in the same child session. The first wrote incorrect content and the second wrote expected content.
- Unit-1 wrote once. One contract and one WorkGraph were submitted; no full replan occurred.
- Before the repair response, the unit-0 target was absent from the base workspace. This supports non-commit of the rejected candidate at that observation point.
- Worker requests retained fixture-reasoner and native effort high.
- Both final files matched expected content; root status reported adaptive Ready.
- Primary storage contained an unsuccessful claim-0 candidate at revision 1, a successful candidate at revision 2, two scope attestations, one verification rejection and one root Ready attestation.
- The repaired scope attestation explicitly bound revision 2 and its patch hash to the same child scope. The other worker's attestation bound revision 1.
- Root repairCount was 0, while the repaired child repairCount was 1. These are scoped counters, not interchangeable totals.
- The fixture supervisor exited 0 and intentionally stopped its Host, which exited 143.

## Evidence

- Session: ses_f815921f7ffediGNR7uopXFs4V
- Run: run-8f8bc71d-e0ce-4f68-a37d-7bdf898ae6d3
- Repaired scope: ses_f8158dcadffeoDj2JGXk6wvj5x
- Log: .tools/validation/restoration-phase44-worker-local-repair.log
- Diagnostic: .tools/validation/restoration-phase44-worker-local-repair.result.json
- Root Ready artifact: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-MY5Zol/state/base-harness/runs/13a3a38b0929c0b4-863e47d9/artifacts/5f/5f043f70d63135398892958604c4cd0fc8744c4687e6c5ef5d16420f9fce23f6.json
- Companion diagnostic record: docs/evidence/WORKER_LOCAL_REPAIR_AND_EVIDENCE_LINEAGE_2026-09-08.json

A bounded read of the fresh run storage visited 60 entries. Five claim-evidence artifacts and the stored scope/root attestations were inspected. The diagnostic and this report are engineering records, not additional Harness Evidence or independent acceptance.

## Open Finding: Selected Evidence Family Remains Disputed

The root Ready selects claim-0 family 6bdead03d102d5ea684225a2cdbf1273894bfd311fb05959bc255b507b046eec, while the same Ready artifact lists that family with status disputed. The successful repaired candidate's family is also listed as disputed.

The observed facts are distinct:
- The old candidate failed its content predicate.
- The repaired candidate and final workspace passed their current content predicates.
- The Ready metadata still associates disputed family status with selected positive evidence.

This is an observed status/selection consistency concern, not proof that the final file contents were wrong or Ready was forged. The artifact alone cannot establish whether disputed deliberately includes historical disagreement or should exclude a family from current selection.

The next investigation must determine how contradiction scope, candidate revision, artifact hash and supersession are represented. An earlier revision's failure should not automatically become an unresolved contradiction of different corrected content. Conversely, genuine unresolved contradictions must not silently count as unqualified support.

Do not change a Ready gate or simply relabel disputed evidence until the family and selection contracts are understood. This finding was not covered by the local-repair diagnostic assertions and remains open despite that diagnostic passing.

## Reproduction

From the repository root with existing pinned runtimes:

```powershell
$env:BASE_HARNESS_PYTHON = Join-Path $PWD '.tools/verifier/Scripts/python.exe'
$env:BASE_HARNESS_DISABLE_MODELS_FETCH = 'true'
$env:BASE_HARNESS_FIXTURE_FAIL_INTEGRATION = '0'
$env:BASE_HARNESS_FIXTURE_REPAIR_WORKER = '1'
$env:BASE_HARNESS_VALIDATION_TAG = 'worker-local-repair-local'
& ./.tools/bun-1.3.14/bun.exe run runtime/script/verify-provider-public-boundary.mjs
```

Choose a unique tag to retain previous logs. Remove the diagnostic repair flag from the shell environment before testing the normal-success path.

## Residual Risk

The provider is scripted and the same implementation agent authored the diagnostic. This is not real-provider reliability or an independent evaluation. The model is not reasoning its way to a repair.

The absence check is a single observation before repair, not continuous filesystem surveillance. The same child session and candidate revision transition were observed; physical Overlay identity was not independently traced.

Two-repair exhaustion, complex multi-file fixes, cancellation, OAuth, long contexts, actual model-specific behavior and cross-platform operation remain outside this run. No full suite, typecheck or live TUI test was run in this diagnostic-only phase. Earlier normal-success/provider-failure results were not rerun after this extension.

The selected disputed-family issue needs investigation before making a broad claim about evidence consistency. Config, dependency and workspace revision hashes in fixture applicability remain unknown, so this Ready must not be reused as proof for another environment.

Existing phase38 titlecase-test and phase40 short-readiness diagnostic issues remain unchanged. No Git operations or push were performed; net_monitor.py was untouched.
