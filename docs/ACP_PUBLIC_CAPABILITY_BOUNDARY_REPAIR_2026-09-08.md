# ACP Public Capability Boundary Repair

## Situation

The previous ACP prompt follow-up restored content requests but introduced two
effort-selector subprocess failures and one negative-test type error. An existing
directory fixture also lacked declared reasoning capability metadata.
This report supersedes those specific unresolved items, not the earlier full Host
regression result.

## Reason

The public provider catalog intentionally contains empty variant option objects.
It separately publishes validated reasoningEfforts.supported names. ACP incorrectly
required private reasoning option payloads from this redacted catalog, so the selector
disappeared. Re-exposing those payloads would weaken the public data boundary.

The Gateway already validates and resolves private native options. A local diagnostic
confirmed a declared low selection reached the request as reasoning_effort=low
and produced a completed assistant response rather than merely HTTP 200.

## Action

- ACP now consumes the Host-advertised native names and requires a matching variant
  entry without re-reading or reconstructing private option payloads.
- Missing capability metadata and reasoning-disabled models expose no named effort.
- Arbitrary labels do not create capabilities, and native spelling is unchanged.
- Gateway private option validation and public provider redaction remain unchanged.
- Directory fixtures explicitly declare supported native levels.
- The negative RPC test uses a structured matcher instead of accessing an unknown type.
- The real ACP content fixture now selects high, resets to provider default,
  changes model and selects max, then checks the actual local model request bodies.

Changed files:

- runtime/packages/base-harness/src/acp/config-option.ts
- runtime/packages/base-harness/test/acp/config-option.test.ts
- runtime/packages/base-harness/test/acp/directory.test.ts
- runtime/packages/base-harness/test/cli/acp/prompt-content.test.ts

## Result

- ACP and provider boundary unit tests: 149 passed, 0 failed;
  350 assertions, 5.46 seconds.
- Real ACP subprocess tests: 12 passed, 0 failed;
  101 assertions, 81.53 seconds.
- Host typecheck: exit code 0.
- No validation watchdog timed out.
- Actual root model requests contained high, no reasoning_effort field, then max.
- Actual request model IDs were test-model, test-model, then second-model.
- Embedded text, image and file-link processing passed.
- Overlapping workspace/private-state paths were rejected before model invocation.

## Evidence

Commands used repository Bun 1.3.14 from runtime/packages/base-harness:

~~~text
bun test --timeout 30000 --only-failures test/acp test/provider/native-reasoning-admission.test.ts test/provider/public-info-projection.test.ts test/provider/reasoning-request.test.ts test/provider/reasoning-capabilities.test.ts
bun test --timeout 30000 --only-failures test/cli/acp/prompt-content.test.ts test/cli/acp/config-options.test.ts test/cli/acp/lifecycle.test.ts
bun run typecheck
~~~

Local stdout/stderr logs use the prefix:
.tools/validation/acp-public-capability-repair-1788870897448

These results use isolated temporary homes and scripted local models. They are
developer diagnostics, not Harness Evidence, Ready artifacts or independent
user validation.

## Residual Risk

- Full Host regression has not been rerun after this repair. Other previously
  reported failures remain separate work; no whole-product pass is claimed.
- A real provider may reject stale or incorrectly configured capabilities.
  The Gateway still fails closed rather than inferring a replacement effort.
- Unsupported variants in old saved sessions require explicit reselection.
- ACP local fixtures do not establish TUI usability, real OAuth reliability,
  provider reasoning quality, long-running stability or independent user success.
- No repository Git operations were performed. net_monitor.py was untouched.
