# Provider Catalog Private Data Preservation

## Situation

The preceding internal/public plugin boundary patch left three failing tests: DigitalOcean catalog URL, OpenRouter configured-model URL inheritance, and Anthropic native thinking-option merging. The previous report correctly recorded those failures; this follow-up supersedes its unresolved-provider status only for the tested scope.

## Reason

Runtime initialization still constructed its private database using toPublicInfo. That deliberately redacted projection removed executable URL and native variant payloads before internal plugin hooks or configured-model merging could preserve them. Fixing the hooks alone was insufficient.

## Action

Changed the catalog-to-database mapping in runtime/packages/base-harness/src/provider/provider.ts from toPublicInfo to the existing private toPluginInfo projection. Added a comment documenting that public redaction belongs at public response boundaries.

No failure assertion was weakened, no provider URL was hardcoded, and no native reasoning level was invented. Public redaction and declared reasoning admission remain unchanged.

## Result

- Bun 1.3.14 targeted provider tests: 520 passed, 0 failed, 1048 assertions across four files, 54.50 seconds.
- Host TypeScript typecheck: exit code 0.
- The three previously failing assertions now pass.
- Local Host + attached headless client + real Python verifier diagnostic: exit code 0.
- Both public metadata routes omit fixture credentials and private payloads while advertising exact high/max effort names.
- Private execution retains fixture authentication and the selected high effort.
- Two WorkUnits execute; the rejected unit repairs once in its original child session, without exposing the rejected write to the base workspace or replanning.
- Successful root verification issues Ready for this synthetic fixture.
- Host health startup: 10.516 seconds; client execution: 29.638 seconds; 14 local model requests. These are individual observations, not comparative benchmarks.

## Evidence

- Targeted test/typecheck terminal session: 62452.
- Test log: .tools/validation/provider-catalog-boundary-1788849013457.log.
- Terminal marker: PROVIDER_BOUNDARY_GATE tests=0 typecheck=0.
- Local Host diagnostic terminal session: 4620.
- Diagnostic result: .tools/validation/provider-catalog-host-1788849095640.result.json.
- Structured companion: PROVIDER_CATALOG_PRIVATE_DATA_DIAGNOSTICS_2026-09-08.json.
- Test files: digitalocean.test.ts, provider.test.ts, transform.test.ts, native-reasoning-admission.test.ts under runtime/packages/base-harness/test/provider.
- This engineering report and companion are diagnostic-only, not Harness Evidence, Ready attestations, or independent user validation.

## Residual Risk

- No real-account OAuth flow, paid provider call, independent user session, or long-duration reliability evaluation was performed.
- The complete Host suite remains unproven beyond the earlier 1401-test run that stopped after 20 failures. Known failures have been addressed in scoped runs; unseen remainder and cross-suite interactions remain.
- The full Core suite has not been rerun after its test-state isolation change.
- Public metadata is intentionally insufficient for direct provider execution; execution must use the trusted internal path.
- Installed plugins remain trusted in-process code. The projection is not a sandbox or deep immutable copy.
- Intentional Host cleanup exited 143; this alone does not prove descendant-process isolation.
- Platform sandboxing, independent packaging, and prior possible user-configuration exposure remain outside this repair.
- No Git operation was performed; net_monitor.py was untouched.
