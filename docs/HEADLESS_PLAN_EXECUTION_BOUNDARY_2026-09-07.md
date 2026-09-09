# Headless plan execution boundary

Date: 2026-09-07

## Situation

The previous restoration proved real Host API plan execution and an interactive TUI
flow. It did not prove the actual headless plan-only command followed by a second
CLI execution command, especially with the hackathon skill or a restarted Host.

This turn tested those entrypoints using the pinned Bun 1.3.14, a local model/MCP
fixture and the actual Python verifier. No paid provider or real account was used.

## Reason

The baseline reproduced three CLI-specific defects:

1. run --plan --format json appended a non-JSON "Plan ready: ..." line.
2. The CLI always sent domain.set=develop, even while executing an existing plan.
   Kernel domain.set correctly clears skills, so this silently removed hackathon.
   The reviewed plan then no longer matched the session and became invalid.
3. The CLI ignored SDK harnessControl error responses and waited for a later model
   idle event that a rejected execution would never produce.

These are Host-client boundary problems. Weakening plan freshness or verification
would not correct them.

## Action

Changed:

- runtime/packages/base-harness/src/cli/cmd/run.ts
- runtime/packages/base-harness/src/cli/cmd/run/harness-output.ts
- runtime/packages/base-harness/test/cli/run-harness-output.test.ts
- runtime/script/verify-headless-plan-flow.ts

The CLI now preserves Host domain/skill selection unless explicitly overridden.
Reviewed-plan execution rejects conflicting settings and requires a selected
existing session. SDK responses are checked before waiting for execution.
Host status events are forwarded as structured JSON; plan_ready and harness_result
have explicit status payloads. Client event subscriptions are aborted and joined
on exit without cancelling an attached Host's run.

The new regression uses actual CLI subprocesses. It covers hackathon plan creation,
an invalid plan ID, execution, an injected integration-provider failure, and a
separate --local mode that requires execution across two Host lifetimes. The local
assertion intentionally remains a required success assertion, not an expected
failure that would disguise missing persistence.

## Result

This implementation is NOT complete or promotion-ready.

| Check | Result |
| --- | --- |
| Host/helper tests | 28 passed |
| TUI typecheck | Passed |
| Host typecheck | Failed: one newly introduced TS2345 argument mismatch |
| Actual plan-only CLI, attached Host | Exit 0; typed plan_ready; all stdout lines valid JSON |
| Wrong-plan CLI | Exit 1 in about 5.5 s; no timeout; reviewed hackathon state preserved |
| Attached CLI execute | Failed: one worker remained running until the 90 s test deadline |
| Attached CLI with integration failure injection | Same worker stall; injection stage not reached |
| Local plan followed by a new local CLI process | Plan succeeds; execute rejects in about 7.1 s |

### Newly introduced type error

At run.ts:876 the call to headlessControls spreads all CLI arguments. The CLI's
message is string[], whereas the shared PlanOptions message field is string.
The runtime control selector does not use message, but the Host typecheck correctly
rejects the call. This is an implementation error introduced in this turn and
was reported rather than silently corrected in a second edit pass.

Next correction: pass only domain, hackathon, plan and executePlan into the selector
instead of passing unrelated CLI arguments.

### Remaining worker stall

Both attached scenarios preserved hackathon and created a new execution run.
The last Host snapshot reported unit-1 completed and unit-0 running, with one
active worker and readyEligible=false.

The Host log shows stream initialization and fixture-reasoner selection for both
children. The fixture request log contains work-unit model requests for unit-1
only. No root integration request was recorded. This narrows investigation to the
model-stream/fixture-request boundary, but does not establish which side is at fault.
Do not claim the provider-failure scenario passed: it never reached its injection.

Do not work around this by dropping hackathon, disabling an independent WorkUnit,
making every graph serial or increasing the deadline.

### Missing cross-process execution

The --local test creates a real plan successfully, exits, then runs a second
in-process Host through the actual CLI. The execution request is rejected, rather
than reaching a terminal execution status.

KernelHost currently keeps its session/contract/plan execution record in memory.
Writing canonical PlanSpec JSON is not by itself an implementation of reviewed
execution restoration. The required persistence/rehydration path still needs work.
A standalone base-harness execute <planId> command is also not registered in the
current CLI entrypoint; only run --execute-plan is currently exposed.

## Evidence

Baseline:

- .tools/validation/restoration-phase20-baseline.json
- .tools/validation/restoration-phase20-baseline-plan.json
- .tools/validation/restoration-phase20-baseline-execute.json

Tests and typechecks:

- .tools/validation/restoration-phase20-gates.json
- .tools/validation/restoration-phase20-host-tests.log
- .tools/validation/restoration-phase20-host-typecheck.log
- .tools/validation/restoration-phase20-tui-typecheck.log

Actual CLI:

- .tools/validation/restoration-phase20-cli-flows.json
- .tools/validation/real-headless-plan-attach.result.json
- .tools/validation/real-headless-plan-attach-plan.json
- .tools/validation/real-headless-plan-attach-wrong-plan.json
- .tools/validation/real-headless-plan-attach-execute.json
- .tools/validation/real-headless-plan-attach-failure.result.json
- .tools/validation/real-headless-plan-local.result.json
- .tools/validation/real-headless-plan-local-execute.json

Attached failure workspace:

```text
C:\Users\doo33\AppData\Local\Temp\base-harness-real-host-KpVSby\workspace
```

In that scenario the reviewed planning run was
run-e893d49f-407c-4406-b5f3-bc1b83e598de and execution began as
run-a182dade-15ae-433e-9672-8be73d3159eb. The selected skill was preserved; execution
still did not finish.

Regression commands, from runtime with BASE_HARNESS_PYTHON set:

```text
bun run script/verify-headless-plan-flow.ts
bun run script/verify-headless-plan-flow.ts --fail-integration
bun run script/verify-headless-plan-flow.ts --local
```

## Residual Risk

- All three end-to-end execution scenarios remain red; the partial successes above
  must not be presented as full TUI/headless parity.
- Host typecheck remains red until the newly introduced argument mismatch is fixed.
- The earlier intermittent Host cleanup timeout is a separate unresolved observation;
  this turn's worker stall is not assumed to have the same cause.
- Live provider/OAuth, cross-platform execution, packaging and the full repository
  suite were not certified by these deterministic fixtures.
- No commit or push was performed. net_monitor.py was untouched.
- All explicitly tracked validation process handles ended. This is not a new
  certification of whole-OS process-tree isolation.
- The overall goal remains active.
