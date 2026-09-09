# Plan Recovery: Redaction Port and Execution Validation

Date: 2026-09-07
Status: Partial. Host startup and explicit-session recovery work; standalone plan resolution still fails.

## Situation

The preceding recovery implementation introduced a direct Host import of
`@base-harness/security/secret-registry`. The Host package does not declare that
dependency; Coordinator already owns it through its persistence boundary.
Consequently, Host loading and SDK generation failed.

## Reason

Plan artifacts need the same run-scoped redactor as Coordinator persistence, not
another Host-level credential dependency. Successful mocked restoration also
needed validation with separate CLI processes, actual workers and the Python
verifier.

## Action

- Added CoordinatorRuntime.redactForPersistence(), delegating to the existing injected PersistenceGateway.
- Wired KernelHost's plan-store redactor through that Coordinator port and removed the invalid Host import.
- Added a port delegation test. No package dependencies were added or installed.
- Successfully regenerated the SDK using its official build script and pinned Bun 1.3.14.
- Ran package typechecks, targeted tests, command help and real local/attached fixtures.
- Diagnosed the remaining standalone command failure using a temporary loopback Host and its actual debug log.
- No second corrective source patch was applied after identifying that separate routing issue.

## Result

| Gate | Result |
| --- | --- |
| Coordinator persistence-port test | 1 passed, 4 expectations |
| KernelHost suite | 37 passed, 149 expectations |
| Host helper/transport suite | 27 passed, 101 expectations |
| Total targeted tests | 65 passed, 0 failed |
| KernelHost, Coordinator, Host, TUI typechecks | Passed |
| SDK generation, formatting and SDK TypeScript build | Passed |
| execute --help | Passed after correcting the validation invocation environment |
| Local plan, Host exit, explicit-session execute | Passed with both workers and real Ready |
| Local restart with root integration Provider failure | Passed: blocked, model_provider_error, no Ready |
| Existing attached plan/execute regression | Passed with both workers and real Ready |
| Local standalone execute <planId> | Failed during plan resolution; not counted as complete |
| Standalone failure/attached-standalone cases | Not reached after the standalone positive case failed |

The first help invocation omitted BASE_HARNESS_LAUNCH_CWD, which the source
installation launcher requires. This was a validation-command mistake, not a
remaining startup defect. The corrected invocation exited zero.

### Actual restart success

- Planning run: `run-d3be7901-f9c9-4068-8ae4-bc56805a6747`
- Fresh execution run: `run-24a5131c-12dd-4a19-af06-76b8e50b47f2`
- Both WorkUnits completed and the final Host status was ready.
- The fixture asserted unchanged provider-native reasoning effort (max), hackathon selection, original contract linkage, no repeated meta reviews, both output files, and actual verifier-attested Criterion/Claim results.
- Ready artifact: `C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-bT3oH9\state\base-harness\runs\d74ba71f3560a953-d6b76c77\artifacts\21\21921d6505485191565964a4a8b7f6c5bfa8fdf72ff0c1b3f351afd3adc44373.json`

### Root integration failure after restart

- Planning run: `run-881ab2d0-d4e4-4af7-a5de-baec5dd83736`
- Execution run: `run-db337eb7-dd22-4f5d-9037-3e1016a9273a`
- Worker commits remained, but the root ended blocked with model_provider_error.
- readyEligible was false and the fixture found no Ready attestation.

### Remaining standalone failure

The original root session resolves with HTTP 200. The new endpoint
`GET /session/harness/plan/<planId>` returns HTTP 500 before reaching plan
resolution.

The actual server log reports:

```text
Expected a string starting with "ses", got "harness"
```

The shared getWorkspaceRouteSessionID() helper treats the segment immediately
after /session/ as a SessionID. It only special-cases /session/status, so the new
static harness namespace collides with that assumption.

Location:
`runtime/packages/base-harness/src/server/shared/workspace-routing.ts:28`

The next change should decode a valid typed session identifier for routing,
return no session hint for static/non-session paths, and leave actual endpoint
validation and authorization intact. It needs regression cases for the plan
namespace and other non-session segments, followed by the original standalone
end-to-end success/failure tests. Do not weaken those tests or substitute the
explicit-session path as the final standalone requirement.

## Evidence

- `.tools/validation/restoration-phase23-gates.json`
- `.tools/validation/restoration-phase23-sdk-codegen.log`
- `.tools/validation/restoration-phase23-execute-help-corrected.log`
- `.tools/validation/restoration-phase23-real-flows.json`
- `.tools/validation/restoration-phase23-secondary-real-flows.json`
- `.tools/validation/restoration-phase23-local-restart.log`
- `.tools/validation/restoration-phase23-local-restart-failure.log`
- `.tools/validation/restoration-phase23-attached-regression.log`
- `.tools/validation/restoration-phase23-local-standalone.log`
- `.tools/validation/restoration-phase23-plan-resolution-debug.json`

The fixture sources retain their original success assertions, including actual
Ready evidence. The failing standalone result remains a failing result.

## Residual Risk

- Standalone plan lookup is not yet functional.
- These tests use deterministic local model/MCP fixtures, not live subscription/OAuth services.
- TUI typechecking is not a new visual/interactive TUI certification.
- This does not certify all platforms, the complete repository suite, sandboxing, or every crash/cleanup case.
- The prior HMAC same-OS-account threat limitation remains.
- No git commands, commits or push were performed. net_monitor.py was not edited.
