# Reviewed Plan Recovery: Implementation Status

Date: 2026-09-07
Status: INCOMPLETE. The current Host cannot load because of an import introduced in this change.

## Situation

The preceding implementation ran an attached plan/execute flow successfully, but a plan saved by a local CLI process could not execute after that Host process ended. KernelHost retained the accepted contract, selected model and graph context only in memory. The standalone execute command was also missing.

## Reason

Plan persistence must preserve reviewed data without serializing Effect bridges, functions, credentials, or prior execution authority. Explicit execution after restart must create a fresh run and independent verifier. It must not resume interrupted workers or infer reasoning-effort names.

## Action

- Added a reviewed-plan store with bounded JSON, an HMAC-sealed recipe, canonical PlanSpec comparison, per-session lookup, and exclusive per-revision consumption markers.
- Persisted the accepted contract, domain/skills, verification policy, original assistant message identifier, provider/model/variant selection, and plan-review provenance.
- Excluded runtime context, provider options and credentials from the recipe. A redactor changing reviewed instructions causes persistence to fail rather than silently executing changed instructions.
- Added KernelHost resolution and restoration APIs. Restoration does not itself dispatch workers or issue Ready.
- Added Coordinator creation of a fresh execution run linked to the original planning run, with contract acceptance by the fresh verifier.
- Added a current-request Host context reconstruction path with provider capability, original message selection and policy checks.
- Added a Host plan-resolution endpoint and a standalone execute command sharing the existing headless implementation.
- Extended the real local plan fixture with a standalone-command option.
- Added eight recovery and tamper/replay-boundary tests.

## Result

| Gate | Result |
| --- | --- |
| KernelHost suite | 37 passed, 0 failed; 149 expectations across 7 files |
| KernelHost typecheck | Passed |
| Coordinator typecheck | Passed |
| SDK generation | Failed before successful regeneration |
| Host and TUI typechecks | Not reached in this gate sequence |
| Host helper tests and execute help | Not reached |
| Real local restart and standalone execution fixtures | Not run against this change |

The blocking error is:

```text
Cannot find module '@base-harness/security/secret-registry'
from runtime/packages/base-harness/src/harness/coordinator-service.ts
```

That direct import was introduced by this change. It is not an established failure of the prior version. The current implementation must not be described as operational or complete.

No corrective second source patch was applied after detecting the error. The proposed next change is to route plan redaction through the Coordinator's existing persistence boundary instead of adding a direct Host dependency. SDK generation and the remaining gates must then be rerun.

## Evidence

- `.tools/validation/restoration-phase22-gates.json`
- `.tools/validation/restoration-phase22-kernel-host-tests.log`
- `.tools/validation/restoration-phase22-kernel-host-typecheck.log`
- `.tools/validation/restoration-phase22-coordinator-typecheck.log`
- `.tools/validation/restoration-phase22-sdk-codegen.log`
- `runtime/packages/kernel-host/test/reviewed-plan-recovery.test.ts`

The successful recovery assertions use deterministic mock Coordinator instances. They do not establish that the actual CLI, Host, workers and Python verifier complete a restarted run.

## Residual Risk

- The new Host import currently prevents startup.
- The new SDK endpoint has not been successfully regenerated or typechecked with its consumers.
- Actual restart execution, standalone execution, attached-flow regression and integration failure handling still need end-to-end validation.
- HMAC protection detects modifications without the signing key; it is not isolation from another process with the same OS-account access to that key.
- Consumption markers deliberately prohibit automatic replay after a crash during execution. No worker auto-resume is added.
- Existing planning-basis coverage and broader platform/provider limitations are not claimed resolved.
- No git commands, commits or push were performed. net_monitor.py was not edited.
