# Plan Revision Persistence and Bounded Liveness Diagnostics

Date: 2026-09-07
Status: Scoped implementation and validation passed. Overall restoration remains in progress.

## Situation

The previous phase introduced fresh planning runs for changed requirements. The
in-memory status included a Host-owned revisesPlan link, but the explicit
Coordinator snapshot serializer omitted it. A test also incorrectly expected a
plaintext goal in a snapshot that intentionally persists goalDigest instead.

Earlier real-flow checks had intermittent Host-readiness and planning waits.
A later successful repeat did not establish their cause or resolution.

## Reason

A reviewed-plan revision needs durable lineage without adding the user goal to
the Coordinator snapshot. Tests must check the actual persistence contract,
rather than weakening it to satisfy a mistaken expectation.

Liveness investigation needs bounded timestamps at Host readiness, model
request receipt, response preparation and CLI settlement. Longer CLI deadlines
or weaker Ready conditions would conceal failures rather than explain them.

## Action

- Persisted revisesPlan alongside executionPlan; retained coordinator-run-v1 and goalDigest.
- Corrected the revised-run test to check the SHA-256 digest, absence of plaintext goal and revision-2 execution.
- Added bounded model HTTP tracing, including catalog requests and handler completion, with a 4096-entry cap.
- Added optional --trace to the real-flow fixture using existing CLI DEBUG logging and bounded Host/client lifecycle events.
- Added a validated BASE_HARNESS_FIXTURE_TAG to preserve phase-specific evidence without overwriting earlier results.
- Tightened Host readiness to an absolute 24-second deadline; the normal CLI deadline remains 90 seconds and wrong-plan rejection remains 20 seconds.
- Kept protocol v4, independent verifier authority, candidate attestation, Overlay protection, native reasoning labels and root-only Ready unchanged.

Changed files:

- [Coordinator persistence](C:/Users/doo33/Downloads/base_harness/runtime/packages/coordinator/src/run-repository.ts)
- [Plan execution regression test](C:/Users/doo33/Downloads/base_harness/runtime/packages/coordinator/test/plan-execution-run.test.ts)
- [Local model/MCP fixture](C:/Users/doo33/Downloads/base_harness/runtime/script/fixtures/local-runtime.ts)
- [Headless real-flow fixture](C:/Users/doo33/Downloads/base_harness/runtime/script/verify-headless-plan-flow.ts)

## Result

### Targeted gates

| Gate | Result |
| --- | --- |
| Coordinator: plan execution, execution lifetime, restored settlement boundary | 17 tests passed; 189 expectations |
| KernelHost suite | 45 tests passed; 187 expectations |
| Host: workspace routing and CLI harness output | 28 tests passed; 67 expectations |
| Total | 90 tests passed; 443 expectations; 0 failures |
| Coordinator, KernelHost, Host and TUI typechecks | All four passed |

Validation used pinned Bun 1.3.14 and the pinned local Python verifier.
No external paid model calls were used.

### Actual CLI/Host flows

| Flow | Client exit codes and elapsed time | Terminal result |
| --- | --- | --- |
| local-positive | plan: 0 (20.91s); revise: 0 (16.00s); execute: 0 (15.63s) | ready |
| attached-positive | plan: 0 (15.80s); revise: 0 (13.14s); wrong-plan: 1 (5.36s); execute: 0 (11.48s) | ready |
| local-provider-failure | plan: 0 (20.73s); revise: 0 (15.97s); execute: 1 (15.60s) | blocked / model_provider_error |
| local-no-debug | plan: 0 (21.13s); revise: 0 (16.44s); execute: 0 (15.39s) | ready |

The three traced flows passed. The additional local control without DEBUG
logging also passed. No client reached its fixed deadline.

Successful flows exercised changed requirements, a fresh revised planning run,
ordinary-text plan revision without mutation, native reasoning selection from
max to high, standalone execution from another directory, two verified worker
outputs and actual independent-verifier Ready evidence. The attached flow also
rejected the wrong plan without consuming a model request.

The Provider-failure case intentionally returned a nonzero execution code,
classified model_provider_error and issued no Ready. Previously verified worker
outputs remained available. These are expected negative-test results.

All four actual revised-run Coordinator snapshots contained the expected
revisesPlan link and matching goalDigest, omitted the plaintext goal property
and retained coordinator-run-v1.

## Evidence

- [Targeted gate exit codes](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-gates.json)
- [Traced-flow execution summary](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-real-flows.json)
- [Actual Coordinator snapshot checks](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-run-persistence.json)
- [Local positive flow](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-local-positive.result.json)
- [Attached positive flow](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-attached-positive.result.json)
- [Provider-failure flow](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-local-provider-failure.result.json)
- [Local no-DEBUG control](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-local-no-debug.result.json)
- [Machine-readable handoff](C:/Users/doo33/Downloads/base_harness/.tools/validation/restoration-phase27-handoff.json)

Each result records client exits, events, model HTTP timestamps, run IDs and
the Ready artifact path where applicable. Trace caps were not exceeded.
The largest fixture response-preparation durations were 7ms, 3ms, 4ms and 3ms
respectively. Handler completion means response preparation, not confirmed
client receipt or model-stream consumption.

Ready artifacts and synthetic workspaces are under per-run temporary
directories; the phase-specific summaries and logs are retained in the
repository's local validation directory.

## Residual Risk

- Earlier intermittent waits were not reproduced here; their root cause is not proven fixed.
- This is not a benchmark or a statistically sufficient liveness sample. DEBUG logging may change timing; one no-DEBUG control only reduces that concern.
- Recovery or explicit discard after an interrupted plan revision remains unsupported by the existing signed-plan flow and needs a separate implementation phase.
- No new interactive or visual TUI certification was performed in this phase; TUI typechecking and shared Host/CLI execution do not replace that check.
- External OAuth, commercial Provider behavior, Linux execution and the complete repository test suite were not validated in this phase.
- Synthetic model fixtures establish protocol and lifecycle behavior, not real-model planning quality.
- GoalContract/verifier common-mode mistakes and same-OS-account tampering risks remain outside this change.
- No git commands, commits or push were performed. net_monitor.py was untouched.

