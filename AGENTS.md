# Base Harness Runtime Agent Rules

## Product boundary

- `runtime/src/cli.ts` only launches the bundled Host; it has no policy authority.
- `runtime/packages/base-harness` owns execution adapters, model/tool invocation and Host API.
- `runtime/packages/kernel` owns pure contract, domain and planning policy.
- `runtime/packages/kernel-host` owns plan persistence and meta-review ports.
- `runtime/packages/coordinator` owns run, scope, scheduler, repair and verifier lifecycle.
- `runtime/packages/workspace` owns instance-scoped Overlay and Candidate transactions.
- `runtime/packages/security` owns redaction, platform containment and sandbox facilities.
- `runtime/packages/tui` only requests and displays Host state.
- `runtime/experiments/minimal-v3` is archived and must not become an alternate product entry point.
- `src/harness/verification_v2.py` alone may promote Evidence or Ready.
- OpenCode, Gajae-Code and Hermes executables are not runtime dependencies.

## Authority invariants

1. Model, tool, MCP, plugin and subagent output is candidate data.
2. State-changing tools require an accepted GoalContract.
3. Tool risk cannot exceed the accepted contract risk.
4. The host creates FailureEnvelope values; actor-supplied envelopes are untrusted.
5. Only the Python verifier may create trusted Evidence and Ready.
6. Verification and protocol failures are fail-closed.
7. Repair is criterion-scoped and bounded.

## Runtime principles

- Keep the agent loop, tool registry and provider registry independent of the CLI.
- Provider capabilities come from provider responses or explicit provider configuration, never model-name guessing.
- Plugins are loaded only from explicit trusted paths.
- MCP tools pass through the same ToolRegistry and Kernel gates as built-in tools.
- Add policy in executable code rather than relying on prompt wording.
- Keep historical documents as provenance, not current runtime authority.

## Preservation

- Keep pre-existing local changes and `net_monitor.py` untouched.
- Re-export bridges must not own a second state store or bypass the Coordinator.
- A rejected contract is not permission to mutate, even in the fast profile.
- A reviewed plan is not Evidence or Ready; only explicit execute may start plan-only work.
