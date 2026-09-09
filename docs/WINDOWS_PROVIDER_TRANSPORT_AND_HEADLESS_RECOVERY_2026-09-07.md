# Windows Provider transport and headless recovery

Date: 2026-09-07

## Situation

The previous headless restoration left a Host type error and two reproducible
attached-CLI worker stalls. Planning and invalid-plan rejection worked, but the
first worker remained running and no root integration occurred. Separate local
plan restoration after Host restart also remained unimplemented.

## Reason

The type error came from forwarding every CLI argument to the control selector:
message was a CLI string array, while the selector's shared option type expected
a string.

For the worker stall, fresh transport tracing distinguished a model/fixture
response problem from a network request that never reached the fixture:

- Host request 8 entered native fetch with a non-aborted signal.
- The fixture did not receive that request.
- Requests 9 and 10 reached the same fixture and received HTTP 200.
- Request 8 remained pending until the diagnostic Host was stopped.
- Repeating the same plan, invalid-plan request and two-worker execution with
  connection reuse disabled completed with real verifier-backed Ready.

This is evidence for a connection-reuse compatibility problem in the tested
Windows/pinned-Bun path. It is not a proven upstream implementation-level diagnosis
and should not be generalized to every operating system or provider.

Bun documents keepalive: false as disabling per-request connection reuse.
The workaround uses that documented transport option rather than changing model
IDs, prompts, worker count or verifier rules. [Bun fetch documentation](https://bun.com/docs/runtime/networking/fetch)

## Action

Changed:

- runtime/packages/base-harness/src/cli/cmd/run.ts
- runtime/packages/base-harness/src/provider/provider.ts
- runtime/packages/base-harness/src/provider/fetch-options.ts
- runtime/packages/base-harness/test/provider/fetch-options.test.ts

The CLI forwards only domain, hackathon, plan and executePlan to headlessControls.
The Provider transport now constructs a fresh per-request init object. Windows
requests disable pooled connection reuse; other platforms retain their existing
preference. Existing header/chunk/overall AbortSignal handling and the existing
Bun idle-timeout setting are preserved.

Tests cover the Windows option, other-platform behavior, unchanged headers/body,
and independent abort signals for parallel requests. The existing full headless
fixtures were not weakened or edited in this turn.

No network diagnostic hooks were left in production. Diagnostic tracing was run
from an ephemeral process wrapper and recorded only request stage, timestamps,
status, signal state and body byte counts, not credentials or request contents.

## Result

| Gate | Result |
| --- | --- |
| Host/CLI/transport unit tests | 32 passed, 0 failed |
| Host typecheck | Passed; previous TS2345 resolved |
| TUI typecheck | Passed |
| Attached CLI plan -> wrong ID -> execute | Passed with real Ready |
| Same CLI with integration-provider failure | Passed: execution exit 1, blocked, no Ready |
| Direct local headless task | Passed with exact file output, MCP use and real Ready |
| Shared Host plan/execute API | Passed with both verified claims |

In the production-code attached scenario, planning took 16.87 s, invalid-plan
rejection 5.49 s, and actual execution 13.05 s. The previous execution was stopped
at its 90 s fixture deadline. These are individual local fixture measurements,
not a general performance benchmark.

Both independent WorkUnits, the hackathon skill, native fixture-reasoner/max
selection and reviewed-plan provenance were retained. Meta reviews were not
repeated on execute. The negative fixture reached its actual root integration
injection this time; it did not merely stop at an earlier worker error.

## Evidence

All validation used repository-pinned Bun 1.3.14, local fake model credentials,
local stdio MCP and the actual Python verifier. No paid model call was made.

Diagnostic traces and A/B comparison:

- .tools/validation/restoration-phase21-transport.result.json
- .tools/validation/restoration-phase21-transport-transport.json
- .tools/validation/restoration-phase21-no-reuse.result.json
- .tools/validation/restoration-phase21-no-reuse-transport.json

Production-code validation:

- .tools/validation/restoration-phase21-gates.json
- .tools/validation/restoration-phase21-host-tests.log
- .tools/validation/restoration-phase21-host-typecheck.log
- .tools/validation/restoration-phase21-tui-typecheck.log
- .tools/validation/restoration-phase21-real-flows.json
- .tools/validation/restoration-phase21-cli-attach.log
- .tools/validation/restoration-phase21-cli-attach-failure.log
- .tools/validation/restoration-phase21-cli-direct.log
- .tools/validation/restoration-phase21-host-api.log

Commands, from runtime with BASE_HARNESS_PYTHON set:

```text
bun run script/verify-headless-plan-flow.ts
bun run script/verify-headless-plan-flow.ts --fail-integration
bun run script/verify-real-host-flow.ts
bun run script/verify-plan-execute-host-flow.ts
```

The successful attached execution links:

- Planning run: run-423f2ad7-e94b-4077-8f8e-8714ebbfc96d
- Execution run: run-7f85cccf-0421-40ea-8cf1-64af8dc800a4
- Ready artifact: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-nwLcD5/state/base-harness/runs/d91de9b838eee07c-3057138d/artifacts/7e/7e6bee9c594787ed25d263928a40aec664dfcecfaa6870f09d12e7a1d3397c20.json

## Residual Risk and Next Implementation

- Local plan -> new Host process -> execute remains unimplemented. This turn did not
  alter or rerun that previously failing persistence path. Its success assertion in
  verify-headless-plan-flow.ts --local must remain intact.
- The standalone base-harness execute <planId> entrypoint still needs implementation.
- Plan restoration must reconstruct fresh Host execution context and revalidate
  plan revision, GoalContract, basis files and model/variant provenance. It must
  not revive stale live-run authority or trust arbitrary workspace JSON.
- Fresh Windows connections can add connection/TLS handshake overhead. Real remote
  provider latency and every custom Provider adapter have not been benchmarked.
- This workaround does not certify Linux behavior, arbitrary provider connectivity,
  whole-OS isolation or the full repository suite.
- The historical intermittent Host cleanup timeout remains a distinct observation,
  not a demonstrated consequence of this worker-stall cause.
- No commit or push was performed. net_monitor.py was untouched.
- All explicitly tracked diagnostic and validation handles exited. The overall
  restoration goal remains active.
