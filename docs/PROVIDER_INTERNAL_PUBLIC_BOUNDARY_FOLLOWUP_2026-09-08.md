# Provider Internal/Public Boundary Follow-up

## Situation

Provider regressions remained after earlier runtime and fixture work. The focused check covers provider catalog loading, configured models, option transformation, and native reasoning admission.

## Reason

Trusted in-process plugin hooks were receiving the public provider projection, which removes executable URLs and native option payloads. Public API redaction must remain separate from internal runtime inputs. This is a concrete boundary concern, but the remaining failing assertions show it was not a sufficient explanation for all observed failures.

## Action

- Added a private plugin-facing provider projection and used it for model, authentication-loader, and small-model hooks.
- Retained the public provider projection and its removal of private URLs and option values.
- Updated transport-override expectations so undeclared reasoning levels are not inferred.
- Added exact, case-sensitive native reasoning admission coverage.
- Declared the reasoning capability needed by the Azure option-filter fixture.
- Added public-projection assertions to the DigitalOcean fixture.

## Result

The already-started targeted command completed with exit code 1.

- Bun: 1.3.14.
- Tests: 517 passed, 3 failed, 520 total across four files.
- Assertions: 1040.
- Test duration: 63.47 seconds.
- Host TypeScript typecheck: exit code 0.
- No additional source correction was applied after these failures were reported.

Remaining failures:

1. DigitalOcean catalog model URL is empty instead of the expected provider URL.
2. One OpenRouter configured model URL is empty instead of the inherited provider URL.
3. Anthropic configured high variant lacks the expected thinking payload.

These observations require further isolation of runtime/catalog behavior versus the expectations at the read boundary. The patch must not be described as a complete provider fix.

## Evidence

- Targeted test and typecheck command terminal session: 32795.
- Log: .tools/validation/provider-private-public-boundary-1788848694215.log.
- Terminal marker: PROVIDER_BOUNDARY_GATE tests=1 typecheck=0.
- Files exercised: test/provider/digitalocean.test.ts, test/provider/provider.test.ts, test/provider/transform.test.ts, test/provider/native-reasoning-admission.test.ts.
- Diagnostic-only engineering results; not Harness Evidence, Ready, or independent user validation.

## Residual Risk

- The three failures remain unresolved.
- No new real-account OAuth or provider request was performed in this follow-up.
- No full-suite success, production stability, or complete absence of reasoning hardcoding is claimed.
- Installed plugins remain trusted in-process extensions; the new projection is not an OS isolation boundary or a deep immutable copy.
- Prior possible user-configuration exposure remains unresolved; this work does not restore or establish the prior contents of those files.
- No Git operation was performed. net_monitor.py was not modified.
