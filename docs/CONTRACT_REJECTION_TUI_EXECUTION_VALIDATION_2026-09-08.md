# Contract Rejection and TUI Execution Validation

Date: 2026-09-08
Phase: 35
Status: concrete runtime progress; promotion gates are not all passing.

## Situation

Phase 34 added Windows snapshot retry handling and rejected execution of blocked
reviewed plans. Its tests exposed a regression: a normal rejected GoalContract
was converted into PLAN_RUN_BLOCKED before its rejection status could be returned.
The previous real TUI attempt had not reached verified completion.

## Reason

A rejected contract and an accepted contract belonging to a terminal run are
different cases. Both must prevent mutation, but a normal contract rejection must
preserve the verifier/runtime result instead of becoming a generic planning error.
Preflight metadata must not permit mutation while runtime acceptance is pending.

## Action

- Changed runtime/packages/kernel-host/src/index.ts so a non-accepted contract
  returns through the existing rejection path before the terminal-run guard.
- Kept the terminal-run guard for accepted contracts and set the preflight mutation
  flag false before awaiting runtime acceptance; it becomes true only after the
  accepted result also passes that guard.
- Preserved the existing rejected-contract regression test and strengthened its
  assertions for contractStatus and outcome.
- Added four cases proving accepted contracts cannot start direct execution when
  the returned phase is blocked, interrupted, failure, or outcome is failure.
- Ran KernelHost tests, the targeted Host control-error tests, and both package
  typechecks serially with the pinned Bun 1.3.14 runtime.
- Ran a native Windows PTY TUI attached to a real Host, local model/MCP fixtures,
  and the real Python verifier. No paid model endpoint was used.
- Saved this report and a diagnostic evidence record. No Git command, commit,
  push, or change to net_monitor.py was performed.

## Result

### Code and test gates

| Gate | Result |
| --- | --- |
| Original rejected-contract regression | Passed |
| Four accepted-but-terminal contract cases | Passed |
| KernelHost test suite | 58 passed, 1 failed |
| KernelHost typecheck | Exit 0 |
| Targeted Host control-error tests | 6 passed, 1 hook failure |
| Host typecheck | Exit 0 |

The KernelHost failure is an EPERM rename in the separate ReviewedPlanStore
atomic writer. It is not the corrected rejected-contract test. The Host failure
is a test hook timeout after its six test bodies pass. Neither remaining failure
was hidden by relaxing assertions or raising the configured 30000 ms timeout.

### Actual TUI recovery and execution

The successful follow-up fixture exited 0. The TUI also exited 0 and emitted
alternate-screen and terminal-mode restoration sequences.

1. Headless plan-only created a reviewed plan without publishing Ready.
2. A new revision was deliberately interrupted while its client process was live.
3. A restarted Host exposed PLAN_REVISION_PENDING rather than resuming execution.
4. The attached TUI showed recovery instructions; its panel and page scrolling
   were exercised at the native PTY size.
5. TUI /plan discard was observed by the Host without a model request.
6. TUI /plan selected plan_once while planningState stayed idle, planOnly was true,
   Ready was false, and both result files were absent.
7. A new ordinary prompt reached plan_ready without creating the result files.
   The restored develop + hackathon selection remained active.
8. TUI /execute missing-plan displayed PLAN_ID_MISMATCH with HTTP 400. The active
   plan, planning run, and absent result files were unchanged.
9. TUI /execute with the reviewed ID opened a distinct execution run, ran two
   WorkUnits, integrated their verified results, and reached root verification.
10. The real verifier produced Ready (adaptive), with both required Claims and
    Criteria verified. The fixture separately checked exact contents of both files.
11. TUI /execute one two was rejected as an invalid local control, and the final
    Host state remained the same ready execution run.

Observed planning run: run-9319cb02-108f-4a11-8d8e-84663889b88d
Observed execution run: run-ef5fd2d4-5f93-47e0-8ed9-65c860d6bd51
Reviewed plan: b8bc500d-792f-4d48-aeac-618ff66f5ac9, revision 1.
Workers: 2 completed. Repairs: 0. Verifier-observed evidence count: 4.

The fixture initially selected the provider-native max effort, then revised with
high. The TUI recovery, new plan, both workers, and root integration sent high.
This establishes value propagation for this fixture, not live provider support.

### Startup and timing observations

The first interactive fixture attempt failed before TUI input. Its cleanup assumed
a successfully registered Host and threw Object.assign(undefined, ...), masking
the primary startup failure. That attempt remains a failure in the evidence.

A separate startup-only diagnostic reached the provider endpoint in
13.46 seconds.
The follow-up fixture started its two Hosts in
10.75 and 7.11 seconds.
The original startup failure's exact cause is not established.

Twenty local samples gave an empty-status median of
20.36 ms and a restored pending-plan
status median of 38.79 ms.
Cold pending status took 106.44 ms.
These are different status paths, not a before/after execution-speed benchmark.

## Evidence

- docs/evidence/CONTRACT_REJECTION_TUI_EXECUTION_VALIDATION_2026-09-08.json
  contains diagnostic outcomes, identities, request metadata, and verifier results.
  It is not a Harness Evidence or Ready artifact and grants no completion authority.
- .tools/validation/restoration-phase35-gates.log contains this phase's test output.
- .tools/validation/restoration-phase35-host-startup-probe.json preserves the
  separate startup observation and captured Host stdout/stderr.
- .tools/validation/restoration-phase35-tui-recovery-followup.result.json contains
  the follow-up fixture result, host/client exits, observations, and model requests.
- .tools/validation/restoration-phase35-tui-control-frames.json contains selected
  raw native PTY control/Ready/exit frames. No desktop screenshot was taken.
- The exact real verifier artifact path is recorded in the diagnostic JSON.

## Residual Risk

- ReviewedPlanStore.atomic still uses its own writeFile-plus-rename path without
  the shared bounded Windows rename policy. One real EPERM occurred in this suite.
- The Host test preload imports AppRuntime during teardown and then disposes it;
  import, disposal, and filesystem-cleanup timings have not yet been separated.
  A hook timeout is confirmed; its exact cause is not.
- The interactive fixture cleanup can mask startup errors before Host registration.
- One streaming PTY chunk was truncated. Selected control and Ready frames, Host
  snapshots, and the final verifier artifact are retained, but this is not complete
  visual coverage of every intermediate frame.
- One successful deterministic fixture does not prove live OAuth/model reliability,
  broad complex-planning performance, Windows storage stress stability, Linux/WSL
  behavior, standalone packaging, or full-product completion.
- The existing independent verifier, candidate attestation, Overlay commit boundary,
  evidence lifecycle, and root-only Ready policy were not weakened.

## Next Work

1. Reuse the shared atomic snapshot writer in ReviewedPlanStore.atomic while
   preserving signature checks and exclusive plan-consumption/publication semantics.
2. Make the validation fixture preserve startup logs and original errors even
   when readiness was never reached.
3. Measure Host teardown phases and fix the actual timeout cause rather than
   treating a longer timeout or a lucky rerun as a solution.
4. Repeat the relevant failure-path gates after those changes; keep overall
   readiness unproven until the remaining requirements have direct evidence.
