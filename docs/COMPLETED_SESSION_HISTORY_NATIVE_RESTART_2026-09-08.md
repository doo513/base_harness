# Completed Session History: Native Restart Validation (2026-09-08)

## Situation
Phase 40 implemented signed session-history restoration, but its full runtime fixture stopped at provider readiness before execution. Later native TUI work produced a completed session with actual Python-verifier Ready, suitable for a fresh Host restart probe.

## Reason
Completed-run context must survive restart without granting present execution or verification authority. Seeing an old Ready in conversation text is not sufficient: the cold Host API and native TUI must expose a clearly historical, read-only summary.

## Action
- Started a new pure-mode Host on a fresh loopback port using the previously completed isolated fixture workspace/state.
- Checked health separately, then queried the session status with a bounded 25-second request instead of the old 2-second provider-readiness assumption.
- Attached the actual native Windows PTY TUI and opened /harness.
- Requested /execute with the already consumed plan ID and inspected the resulting error and subsequent Host state.
- Exited the TUI and intentionally stopped the owned Host.
- Made no production or test source changes.

## Result
All nine scoped checks passed:
- The cold Host restored previous run run-29d2b59e-6cff-4494-b8c9-8584820aae80.
- develop + hackathon survived restart.
- The previous run was historical Ready with readOnly=true and revalidated=false.
- Current phase stayed inactive, current runId empty, Ready eligibility false, and active workers/evidence empty.
- Historical evidence count remained 4, with two completed workers.
- TUI displayed HISTORY READY and explicitly stated that the current workspace was not reverified.
- TUI also restored the visible Fixture reasoner / max selection.
- Replaying the consumed plan produced PLAN_ALREADY_CONSUMED / HTTP 400.
- The rejection did not open a current execution run or change historical authority.

Cold status request: 798.28 ms.
TUI exit: 0 with terminal restoration sequences.
Host shell exit: 1 after intentional Ctrl+C. No matching owned Bun Host process remained in the subsequent exact command/port check. This is not a graceful-shutdown or complete descendant-process-tree proof.

## Evidence
The companion JSON records cold and post-rejection snapshots, selected PTY frames, scoped checks and process observations.
The prior native execution report is NATIVE_TUI_MODEL_PLAN_EXECUTION_FOLLOWUP_2026-09-08.md.
The original phase-40 full-fixture readiness failure remains historical evidence; this separate successful probe does not rewrite that failed run as passed.

## Residual Risk
- One completed Ready session with unchanged fixture files was tested. Changed-file, blocked, direct-run and broader restart matrices are not established by this probe.
- The current state intentionally does not claim that old verified artifacts still prove the workspace.
- No live account, external model, Linux/WSL or standalone packaging validation was performed.
- Captured PTY frames are not desktop screenshots or comprehensive layout coverage.
- No general startup-performance or full-product completion claim is made.
- Git and net_monitor.py were untouched.
