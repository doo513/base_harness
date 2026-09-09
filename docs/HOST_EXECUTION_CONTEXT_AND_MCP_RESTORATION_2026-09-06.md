# Host execution context and MCP restoration

## Situation

The previous real planned-flow gate stopped before its first meta-review model request with `InstanceRef not provided`. Standalone workspace and Host typechecks also had one narrowing error each. MCP tool IDs were classified as unknown during planning, even when their configured catalog descriptor explicitly declared a non-destructive read.

## Reason

- Task executors shared an Effect bridge captured during service initialization instead of the actual request.
- Kernel tool classification only knew built-in tool IDs; MCP catalog operation metadata was not forwarded to the planning gate.
- Isolated policy tests did not establish that actual Host workers could complete their lifecycle.

## Action

- Added a Host-only request execution context with a private Symbol and WeakMap identity, bound to the originating session and workspace.
- Captured that context for root prompts, GoalContract proposals and WorkGraph proposals.
- Forwarded it through meta-review, worker and root integration/repair callbacks rather than a service-initialization bridge.
- Kept meta-review dispatch authority separate from execution context; Actor flags or serialized context do not grant authority.
- Fixed both TypeScript narrowing errors without changing their runtime decisions.
- Forwarded typed MCP operations to the Kernel gate. Only explicit readOnlyHint=true and destructiveHint=false classify a tool as read; missing or contradictory hints remain unknown.
- Applied MCP scope checks before resource/tool execution. An MCP descriptor does not grant worker, explore or meta-review permissions.
- Kept tool permission prompts, Candidate attestation, Overlay publication and root-only Ready authority in place.

## Result

| Gate | Observed result |
| --- | --- |
| Workspace typecheck | Passed |
| KernelHost typecheck | Passed |
| Host typecheck | Passed |
| Workspace tests | 28 passed, 1 POSIX-only skip, 0 failed |
| KernelHost tests | 24 passed, 0 failed |
| Host context, dispatch and MCP boundary tests | 11 passed, 0 failed |
| Real direct Host flow | Passed; local model HTTP, stdio MCP, actual Python verifier and Ready artifact |
| Real planned Host flow | Failed after successful contract review, MCP call and plan review; worker execution remained incomplete |
| Live Host API follow-up | Both WorkUnits were created but failed; final message was Task cancelled, outcome blocked, no Ready |

The current run therefore establishes 63 passing TypeScript tests and three passing typechecks, not full restoration completion. The unrelated package suites and Python suite were not rerun in this phase.

The direct smoke test made six fixture model requests and completed in 22,742 ms. The failed planned smoke made eight requests and completed in 41,883 ms. These are local diagnostic durations, not production performance or cost benchmarks.

## Evidence

- `.tools/validation/restoration-phase14-gates.json`
- `.tools/validation/restoration-phase14-real-flows.json`
- `.tools/validation/restoration-phase14-planned-flow.log`
- `.tools/validation/restoration-phase14-direct-flow.log`
- `.tools/validation/restoration-phase14-live-statuses.json`
- `.tools/validation/restoration-phase14-live-refreshed-statuses.json`
- `runtime/packages/base-harness/test/harness/execution-context.test.ts`
- `runtime/packages/base-harness/test/harness/mcp-operation.test.ts`

Pinned runtime: Bun 1.3.14. The real flow used `.tools/verifier/Scripts/python.exe`, not a mocked VerificationClient. Credentials and model responses were local fixtures; no paid model or real account was used.

## Residual Risk

- Worker cancellation remains unresolved. The next change must trace request abort signals and background-job/Effect scope ownership, then rerun the full worker -> candidate verification -> commit -> integration sequence. The observed message alone does not establish its precise cause.
- Root repair context transport is covered in a focused test, but real planned repair was not reached.
- A direct API credential write initially left the fixture provider returning 401. Disposing the Host instance before the next request allowed authentication. Authentication cache invalidation needs a separate parity check.
- MCP annotations describe a configured server's contract; they do not prove that its implementation is side-effect free or provide OS isolation.
- The TUI was not interactively retested in this phase. Changes use the shared Host path, but that is not a substitute for TUI/headless parity evidence.
- Real OAuth/provider compatibility, complete process isolation and production cost improvements are not established by these fixtures.
- No new verification authority, Ready bypass or model reasoning-effort vocabulary was added.
- No commit or push was performed. `net_monitor.py` was not read or modified.

