# Git type repair and Host startup observation (2026-09-08)

## Situation

Three branded-path comparison errors remained in the new Git tests even though the preceding full Core runtime run passed. A real Host follow-up was also needed because static checks alone do not demonstrate that the application starts and executes work.

## Reason

Repository path fields use the AbsolutePath brand. The test expectations supplied plain strings. Constructing those expected values with AbsolutePath.make retains exact equality and the existing type contract.

## Action

- Updated three expectations in runtime/packages/core/test/git.test.ts with AbsolutePath.make.
- Ran the Git and catalog test files and the full Core typecheck.
- Ran the existing local deterministic provider/MCP/real Python verifier diagnostic in its two-worker local-repair mode.
- After the first Host reached its 30-second health deadline and was terminated, ran a separate diagnostic with the existing bounded startup tracer enabled.
- Kept distinct tags and artifacts for the failed and successful attempts. No startup timeout was increased and no runtime source was changed in this step.

## Result

| Check | Result |
| --- | --- |
| Git and catalog tests after type correction | 20 pass, 0 fail; 62 assertions |
| Core typecheck after type correction | Exit 0 |
| Previous full Core runtime run | 1109 pass, 7 skip, 0 fail; not repeated after the three test-only edits |
| Host attempt without tracing | Failed health readiness after 30.172 seconds; no model requests |
| Separate Host attempt with tracing | Ready after executing the local-repair scenario |

The previous syntax and branded-path test errors are resolved.

The successful Host attempt established the following scoped behavior:

- Public provider/config routes omitted fixture credentials and private request options, while preserving the exact high/max effort choices.
- Two workers used the restricted structured-tool catalog.
- The rejected first worker candidate was absent from the real workspace before repair.
- Only unit-0 was repaired, once, in the same child session; unit-1 wrote once without repair.
- No full replanning occurred.
- The actual Python verifier and Host completion flow ended with root Ready and public planningState=idle.
- Fourteen deterministic model requests were recorded. The headless client exited 0; the Host was deliberately stopped with exit 143.

Successful execution run: run-2a6e64f5-2f0d-4d42-b585-932bf9dff0fe.

## Evidence

- Pinned repository-local Bun 1.3.14 and .tools/verifier/Scripts/python.exe.
- Targeted gate: GIT_PATH_TYPE_REPAIR tests=0 typecheck=0.
- Failed diagnostic: .tools/validation/git-discovery-host-repair-1788844228521.result.json.
- Successful diagnostic: .tools/validation/git-discovery-host-trace-1788844367523.result.json.
- Successful Host startup trace: .tools/validation/git-discovery-host-trace-1788844367523-host.stderr.log.
- Companion diagnostic JSON: GIT_TYPE_REPAIR_AND_HOST_STARTUP_OBSERVATION_2026-09-08.json.

The successful attempt measured health readiness at 17.365 seconds and headless execution at 29.297 seconds. Its trace measured:

- launcher.import_start to cli.modules_ready: 7040 ms.
- runtime.import_start to runtime.import_ready: 6235 ms.
- host.handler_start to host.module_ready: 2196 ms.
- provider.env_ready to provider.credentials_ready, after listening: 1245 ms.

These trace spans locate observed delay in this successful attempt. They do not establish the cause of the preceding untraced timeout, nor prove that enabling tracing fixed anything.

## Residual Risk

- Startup remains variable: one attempt failed the 30-second readiness gate and the next succeeded. The failure is not overwritten by the later success.
- The failed attempt's Host stdout/stderr were empty, so its blocking stage is unknown.
- CLI/runtime module loading is a concrete profiling target, but one traced sample is insufficient for a causal or performance guarantee.
- No timeout extension or early misleading health response should be substituted for actual runtime readiness.
- Real OAuth accounts and genuine model workload quality were not validated; all model responses were deterministic local fixtures.
- Seven skipped Core cases, cross-platform coverage, distribution packaging, and long-duration reliability remain outside these results.
- Diagnostic reports are not Harness Evidence/Ready or independent user validation. A fixture run's actual root Ready only applies to that fixture contract.
- No repository commit or push was performed. net_monitor.py was not touched.

