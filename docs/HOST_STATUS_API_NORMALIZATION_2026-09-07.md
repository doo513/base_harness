# Host status API normalization

Date: 2026-09-07

## Situation

The preceding restoration recovered the real TUI plan-only -> execute -> Ready path.
Its new Host API regression still failed before execution: manual verification
returned no planningState, although GET /session/:id/harness returned plan_ready.
This was an API contract discrepancy, not missing planning functionality in the TUI.

## Reason

The Host Coordinator facade routed status, control and subscriptions through
KernelHost. verifyRoot, the verify alias and cancel instead fell through to the raw
Coordinator runtime. Their results omitted domain, skills, planning and meta-review
state. A client could therefore receive different views after reading or operating
on the same session.

The correction belongs at the shared Host boundary. Clients must not invent missing
planning state, and the verifier must not acquire presentation responsibilities.

## Action

- Added a shared runtimeStatus response boundary in the Host Coordinator facade.
- Routed verifyRoot, verify and cancel through that boundary after their runtime
  operation completes. Responses use the same current Kernel-enriched view as GET.
- Kept runtime execution, failure propagation, cancellation and Ready authority
  unchanged. No new model or reasoning-level mappings were added.
- Added four tests using the real Host facade for both verify entrypoints,
  cancellation and control/event/read consistency.
- Preserved the formerly failing plan_ready assertion in the real Host API fixture.
- Strengthened the fixture to compare complete manual-verification and GET snapshots.
- Added a separate plan-cancellation scenario, including a subsequent manual verify,
  zero worker execution, no workspace result files, no additional model requests
  and no Ready artifact.

Changed source files:

- runtime/packages/base-harness/src/harness/coordinator-service.ts
- runtime/packages/base-harness/test/harness/coordinator-status.test.ts
- runtime/script/verify-plan-execute-host-flow.ts

## Result

| Gate | Result |
| --- | --- |
| Host boundary tests, catalog fetching disabled | 23 passed, 0 failed; 4.89 s |
| Host typecheck | Passed; 16.22 s |
| TUI typecheck | Passed; 6.17 s |
| Real Host plan-only -> execute | Passed; 31.34 s |
| Real Host integration-provider failure | Passed; 29.36 s |
| Real Host plan cancellation | Passed; 22.03 s |
| Same 23 Host tests in the default fetch environment | Passed, no cleanup timeout; 4.92 s |

The successful execution used two actual Overlay workers, actual Python verification,
a fresh execution run and a real Ready artifact for both required claims. The local
fixture made 12 model requests; the native fixture-reasoner/max selection remained
intact through review, workers and integration. Meta reviews were not repeated at
execute, and internal integration instructions remained synthetic.

The integration-failure scenario ended blocked with model_provider_error, preserved
both already verified and committed files, and produced no Ready. Manual verification
did not clear the failure.

The cancellation scenario ended interrupted in the original planning run. Its seven
planning requests did not increase after cancellation; neither result file, worker
execution nor Ready was created. Its artifactMatches=false diagnostic is intentional:
cancellation requires the output files to remain absent, not to match successful output.

The earlier cleanup timeout did not reproduce even without disabling model fetching.
This does not establish its root cause or prove that it is fixed. Test preload and
production cleanup code were not changed.

## Evidence

Validation used the repository-pinned Bun 1.3.14 and the existing local Python verifier.
No paid external model or user account credentials were used.

Commands, from runtime with BASE_HARNESS_PYTHON set:

```text
bun run script/verify-plan-execute-host-flow.ts
bun run script/verify-plan-execute-host-flow.ts --fail-integration
bun run script/verify-plan-execute-host-flow.ts --cancel-plan
```

Host/TUI typecheck and package-cwd test invocations are recorded with their outputs:

- .tools/validation/restoration-phase19-gates.json
- .tools/validation/restoration-phase19-host-status.log
- .tools/validation/restoration-phase19-host-typecheck.log
- .tools/validation/restoration-phase19-tui-typecheck.log
- .tools/validation/restoration-phase19-host-api.json
- .tools/validation/restoration-phase19-plan-execute.log
- .tools/validation/restoration-phase19-plan-integration-failure.log
- .tools/validation/restoration-phase19-plan-cancel.log
- .tools/validation/restoration-phase19-host-default-env.json
- .tools/validation/real-host-plan-execute.result.json
- .tools/validation/real-host-plan-execute-failure.result.json
- .tools/validation/real-host-plan-cancel.result.json

Successful run identities:

- Planning: run-80ca67be-6e16-4ae1-84d5-33b1bb156d91
- Execution: run-ee5609dd-7500-4c8c-b88b-049582eb0160
- Root session: ses_f84978e6dffeSeulB8txO8xlkQ
- Ready artifact: C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-mqY6zH\state\base-harness\runs\b26e2d2c66758c26-54231a7d\artifacts\dd\dd7a24a608c66620a53990a261f9373d2d1ecf159e3f994c21035fc9a65324e3.json

## Residual Risk

- The historical Host cleanup timeout is not reproduced or causally explained.
  Do not claim that a model-fetch environment flag fixes it.
- This turn exercised the shared real Host API and real verifier, not another PTY
  session. The preceding report contains the actual interactive TUI evidence.
- Local deterministic fixtures do not certify live OAuth/provider connectivity,
  arbitrary complex projects, Linux behavior, OS sandboxing or real-model quality.
- No full monorepo suite or packaging promotion was run in this turn.
- No commit or push was performed. net_monitor.py was not touched.
- The overall restoration goal remains active; these are targeted completion
  results, not a claim that every product requirement is proven.
