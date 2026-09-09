# ACP Prompt and Native Reasoning Follow-up

## Situation

The remaining embedded-content subprocess test returned a generic ACP session error.
The preceding lifecycle repair was retained. This follow-up is incomplete.

## Reason

A bounded local diagnostic using the real ACP process and Host HTTP endpoint found:
- HTTP 500 with SESSION_STORE_PATH_INVALID in the Host log, before any model request.
- The test used the isolated home itself as the workspace. Host-private session state
  was inside that workspace, which violates the existing storage boundary.
- Separating the workspace exposed another failure: ACP selected the first variant
  label (low) without a declared native reasoning capability. The Gateway rejected it.

These were separate failures; HTTP 200 alone was not treated as successful completion.
The second diagnostic returned an assistant error despite the HTTP 200 response.

## Action

- Kept the Kernel session-store boundary unchanged.
- Separated the positive ACP fixture workspace from Host-private state.
- Added a negative test requiring rejection before any model call when paths overlap.
- Added explicit local-fixture image modality and named reasoning option declarations.
- Kept provider default when no native effort is selected or the model changes.
- Added an explicit provider-default reset and preserved exact native spelling.
- Restricted ACP effort admission using structured capability data.
- Added request-content and selection-reset assertions.

Runtime files changed:
- runtime/packages/base-harness/src/acp/config-option.ts
- runtime/packages/base-harness/src/acp/directory.ts
- runtime/packages/base-harness/src/acp/service.ts

Fixture and test files changed:
- runtime/packages/base-harness/test/cli/acp/helpers.ts
- runtime/packages/base-harness/test/cli/acp/config-options.test.ts
- runtime/packages/base-harness/test/cli/acp/prompt-content.test.ts
- runtime/packages/base-harness/test/acp/config-option.test.ts
- runtime/packages/base-harness/test/acp/service-session.test.ts

## Result

The changes are NOT ready for promotion.

- ACP unit tests and native reasoning admission: 131 passed, 1 failed;
  281 assertions, 7.22 seconds.
- ACP lifecycle, config selection and prompt subprocess tests: 10 passed, 2 failed;
  80 assertions, 90.53 seconds.
- The embedded text, image and linked-file prompt test passed.
- The overlapping Host-state/workspace negative test passed without a model request.
- Host typecheck failed with one TS2339 in the new negative test.

## Evidence

All commands used repository Bun 1.3.14, isolated fixture homes and local scripted
model responses. No paid model call was made. All child validation processes
terminated normally without watchdog timeout.

Commands from runtime/packages/base-harness:

~~~text
bun test --timeout 30000 --only-failures test/acp test/provider/native-reasoning-admission.test.ts
bun test --timeout 30000 --only-failures test/cli/acp/prompt-content.test.ts test/cli/acp/config-options.test.ts test/cli/acp/lifecycle.test.ts
bun run typecheck
~~~

These are developer diagnostics, not Harness Evidence, Ready artifacts or
independent user validation. The earlier full Host regression remains failed;
it was not rerun here.

## Residual Risk

1. The new ACP capability helper incorrectly rechecks private option payloads on
   the public provider catalog. public-info.ts intentionally emits empty variant
   option objects while preserving reasoningEfforts.supported. As a result,
   two subprocess effort-selector tests fail because the selector disappears.
   Corrective direction: consume the Host-advertised supported names in ACP,
   retain private option validation in the Gateway, and do not expose private
   provider options through the public API.
2. The existing directory unit fixture has variant mappings but lacks
   reasoningEfforts metadata. Its test must explicitly distinguish declared
   capabilities from arbitrary labels.
3. The new negative test accesses code on an unknown RPC error type.
   It needs a structured matcher or type narrowing, not an unchecked cast.
4. Old sessions carrying unsupported stored variants need explicit reselection;
   silent remapping is not a valid migration.
5. Successful local fixtures do not establish real-provider reliability or
   independent practical task-completion quality.

No repository Git operations were performed. net_monitor.py was untouched.
