# Phase 13 — Thin Terminal UI

Status: IMPLEMENTED as a launcher/monitor; interactive runtime approvals remain a separate follow-up gate.

## Problem / evidence

The integration runtime is configurable from the CLI, but real development/hackathon use benefits from a persistent terminal surface for selecting a workspace/run, entering a goal, monitoring progress, and resuming/inspecting previous runs. Re-implementing runtime policy inside the TUI would create a second execution authority and risk divergence from the CLI/Kernel.

## Contract

- the TUI is a thin client over `python -m harness.cli`;
- it never executes model/tool/oracle logic itself;
- workspace/profile/config/goal/budget/security choices are converted into ordinary CLI arguments;
- arguments are passed as an argv list, not shell interpolation;
- monitoring reads only the runtime's persisted `metrics.json`, `events.jsonl`, and `tool_calls.jsonl`;
- malformed/partially-written monitor files are tolerated as display failures and never alter runtime state;
- Ctrl-C terminates the launched CLI process rather than mutating checkpoints directly;
- runtime approval authority is not fabricated by the TUI v1.

## Implementation

Added `harness.tui` with:

- `new`: interactive new-run launcher;
- `resume`: interactive resume launcher;
- `inspect <run_dir>`: read-only persisted run summary;
- workspace/config/profile/goal/acceptance/max-step/execution-backend/network/security prompts;
- subprocess launch using `sys.executable -m harness.cli` and argv values;
- asynchronous stdout/stderr collection;
- periodically refreshed terminal dashboard;
- persisted metrics, recent events, and recent tool-call summaries;
- robust handling of files that are absent, malformed, or mid-write while a run is active.

Launch with:

```text
python -m harness.tui new
python -m harness.tui resume
python -m harness.tui inspect ./run
```

## Structural review

- the TUI has no reference to `HarnessState`, `ActionRuntime`, verifiers, recovery, or completion oracles;
- all execution continues through the existing CLI/runtime composition path;
- TUI monitoring is read-only;
- command arguments are never concatenated into a shell command;
- no secret value is requested directly by the TUI: provider/MCP credentials continue to resolve from configured secret references.

## Validation focus

`tests/test_integration_tui.py` covers:

- argv-safe CLI command construction, including paths/goals containing spaces;
- propagation of strict layout/isolation/network/acceptance choices;
- reading persisted metrics/events/tool calls;
- graceful handling of malformed/partially-written live monitor files.

## Known limitation: approvals

MCP tools default to `permission=confirm`, but the current runtime constructor/CLI does not expose an interactive approval callback contract. TUI v1 therefore does **not** pretend to approve these tools. Such calls remain denied/approval-required unless the operator explicitly configures a different policy.

A future approval implementation should add one Kernel-owned approval request/response contract, persist the approval decision/provenance, and let both CLI/TUI consume that contract. It should not special-case MCP execution inside the TUI.
