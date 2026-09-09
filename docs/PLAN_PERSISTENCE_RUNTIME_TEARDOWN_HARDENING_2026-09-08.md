# Reviewed Plan Persistence and Runtime Teardown Hardening

Date: 2026-09-08
Phase: 36
Status: selected regression gates pass; full-product readiness remains unproven.

## Situation

Phase 35 repaired normal contract rejection and completed a native TUI recovery,
plan-only, exact-execute, and real Python Ready scenario. Three concrete problems
remained: ReviewedPlanStore could fail a Windows rename without bounded retry;
pure Host tests timed out during teardown; the interactive fixture could mask
a pre-readiness Host failure with Object.assign(undefined, ...).

## Reason

The plan store should reuse the already-tested atomic writer, not invent another
recovery policy. Its signed revision decisions and exclusive execution markers
must remain distinct from replaceable snapshot files.

Pure tests should dispose an application runtime if it was loaded, not import
the complete provider/tool/plugin graph solely to dispose an unused runtime.
A cleanup failure must never erase the primary diagnostic failure.

## Action

- Connected ReviewedPlanStore.atomic to the shared Workspace atomic snapshot writer.
  Added the package dependency, regenerated bun.lock, and completed installation
  using Bun 1.3.14 with frozen lockfile and lifecycle scripts disabled.
- Preserved size limits, path checks, HMAC signatures, and hard-link-based exclusive
  revision publication and consumption.
- Reject a false/invalidation result from the snapshot writer instead of treating
  it as a published file.
- Added deterministic tests for transient head-cache locks, persistent head-cache
  locks, failed canonical revision publication, and invalidated writes.
- Added a dependency-free runtime finalizer registration module. AppRuntime
  registers its disposer on load; both its public dispose function and test
  teardown share one pending cleanup operation.
- Kept cleanup failures observable and prevented replacement of an existing
  registered disposer. Pure test teardown no longer imports AppRuntime.
- Added cleanup tests, including an isolated child process that loads the real
  AppRuntime and confirms the same cleanup promise is used.
- Guarded recursive test scratch cleanup against paths outside the process-specific
  temporary directory.
- Recorded validation Hosts immediately after spawn, before readiness succeeds.
  Kept primary errors and separately recorded cleanup failures; created the log
  directory when needed.
- Added a validation-only forced-startup-failure switch and exercised it against
  a real spawned Host process.

## Result

### Final selected gate results

| Package or probe | Result |
| --- | --- |
| Workspace tests | 34 passed, 1 POSIX-only skip |
| Coordinator tests | 43 passed |
| KernelHost tests after dependency installation | 63 passed |
| Host control/lifecycle tests after dependency installation | 12 passed |
| Selected TUI tests | 69 passed |
| Typechecks for all five packages | Exit 0 in each package's final run |
| Same six Host control tests, separately timed | 6 passed |
| Correctly configured CLI --help and run --help | Both exit 0 |
| Forced pre-readiness startup failure | Expected failure preserved and cleanup probe passed |

These package results total 221 passing selected tests and one Windows skip.
The separate six-test timing rerun is not added to that total.
The table is not a claim that the repository's entire test suite passed.

### Persistence semantics

A transient Windows head-cache lock is retried while the old destination remains
intact. A permanent lock is still an error after the existing bounded attempt
limit; the destination is never deleted or overwritten via a copy fallback.

A signed revision decision may already have been durably published before its
replaceable reviewed-head cache update fails. In that case, recovery follows the
signed decision and canonical plan; it does not invent a new review or execution.
The new test fixes this distinction explicitly.

If the canonical revision cannot be published, the revision remains pending and
non-executable until explicit discard/recovery. The existing single-winner
publication and single-consumer execution tests also pass.

### Teardown observations

The isolated pre-change probe measured runtime import at approximately
3.44 seconds,
runtime disposal at 0.79 ms,
and scratch removal at 156.07 ms.

That probe did not reproduce the full earlier hook timeout. The evidence supports
removing an unnecessary cold import, not attributing every earlier delay to it.

After the change, the exact six-test Host control set completed successfully in
1.28 seconds including command overhead.
No timeout increase or assertion weakening was used. The broader 12-test Host
selection additionally loads the real runtime in an isolated child process and
also passes. This is test lifecycle improvement, not a measured LLM-task speedup.

### Startup failure diagnostics

The forced startup probe produced the intended startup error, an exit record for
the spawned Host, no Ready, no model requests, and an empty cleanupFailures list.
The fixture itself correctly exited 1; the outer assertion probe exited 0 because
this expected failure was preserved. It is not reported as a successful task run.

### Setup errors retained in the evidence

The first test run occurred after lockfile-only generation and could not resolve
the newly declared package-local Workspace dependency. Installing the frozen
lockfile resolved the link; affected tests and typechecks were rerun successfully.

The first source-launcher help probe omitted BASE_HARNESS_LAUNCH_CWD. The subsequent
probe supplied the launch directory and both help commands exited 0. Neither
setup error was hidden by changing production behavior.

## Evidence

- docs/evidence/PLAN_PERSISTENCE_RUNTIME_TEARDOWN_HARDENING_2026-09-08.json
  records package outcomes, setup failures, timing observations, and the forced
  startup failure result. It is diagnostic data, not Harness Evidence or Ready.
- .tools/validation/restoration-phase36-initial-gates.log
- .tools/validation/restoration-phase36-linked-gates.log
- .tools/validation/restoration-phase36-entrypoints.log
- .tools/validation/restoration-phase36-teardown-probe.json
- .tools/validation/restoration-phase36-forced-startup.result.json
- The phase35 report records the prior native TUI end-to-end Ready observation:
  docs/CONTRACT_REJECTION_TUI_EXECUTION_VALIDATION_2026-09-08.md.

## Residual Risk

- Windows permissions or locks that outlast the bounded retry window remain errors.
- The entire cause of the previous test hook timeout is not proven; loaded-service
  cleanup under broader real workloads still needs its own coverage.
- Native TUI end-to-end execution was not repeated in this phase. Phase35 evidence
  remains historical and must not be mislabeled as a phase36 run.
- Live OAuth/provider reliability, Linux/WSL behavior, independent packaging, all
  repository tests, and broad complex-task success rates are outside this phase's
  demonstrated results.
- No new meta-review layer or model calls were added by these changes.
- No Git operation, commit, push, or modification of net_monitor.py was performed.

## Next Work

1. Use a normal source-run recovery/execution scenario to cover the final installed
   environment after this storage/lifecycle change.
2. Audit the remaining agreed runtime/UI requirements against current evidence
   instead of treating selected green tests as full-product completion.
3. Keep failure classification, candidate attestation, and root-only Ready intact
   while resolving any further concrete execution failures.
