# Base Harness Runtime V3 refoundation

## Situation

The V2 product embedded an OpenCode-derived workspace containing TUI, server, ACP, session, provider, SDK and plugin packages. Base Harness verification behavior existed, but its execution identity and failure surface remained coupled to the inherited runtime.

## Reason

Base Harness needs to own the complete actor loop and tool boundary for GoalContract, Evidence and Ready to be enforceable product behavior rather than a plugin rule. Repeated adapter work also obscured the verification differentiator.

## Action

1. Removed the OpenCode-derived `runtime/` workspace and all inherited TUI, server, ACP and SDK packages.
2. Added a small Bun runtime with an explicit AgentLoop, ToolRegistry and ProviderRegistry.
3. Added OpenAI-compatible provider profiles with model-catalog discovery and provider-reported reasoning capabilities.
4. Added bounded file tools, structured argv execution, MCP registration, explicit trusted plugins, skills and read-only subagents.
5. Connected runtime actions to the existing protocol v4 Python sidecar.
6. Kept GoalContract-before-mutation, structured risk, host-created FailureEnvelope, bounded repair and verifier-only Ready.

## Result

The source tree now expresses one independent product flow instead of an OpenCode fork with Base Harness patches. A model is connected as a provider, tools are supplied by Base Harness, and all state-changing calls cross the verification kernel.

## Evidence

- `runtime/src/agent/loop.ts` owns the actor loop.
- `runtime/src/tools/registry.ts` owns tool schemas and dispatch.
- `runtime/src/providers/registry.ts` owns provider adapter discovery.
- `runtime/src/kernel/index.ts` owns contract, risk, action and completion gates.
- `runtime/src/verification/client.ts` is the sole runtime-side protocol v4 bridge.
- `src/harness/verification_v2.py` remains the Evidence and Ready authority.

No test or typecheck result is claimed in this report because this refoundation was not validated during the edit turn.

## Residual Risk

- The initial provider surface is OpenAI-compatible only; native OAuth adapters are not included.
- The CLI is intentionally simple and is not a full-screen TUI.
- MCP and trusted plugins execute in the host process and still need an OS sandbox boundary.
- File mutation is atomic per file but candidate Overlay and multi-file rollback are not yet restored.
- The LLM still proposes semantic GoalContract content; deterministic binding checks do not prove that its interpretation is uniquely correct.
- The runtime source must pass installation, typecheck, protocol integration and real-provider smoke gates before release use.

## Reference

The architecture was informed by the public Hermes Agent separation of agent loop, provider resolution, central tool registry and toolsets. Hermes Agent is MIT licensed. No Hermes implementation file was copied.
