# Base Harness

An independent verification-first harness, using its own Kernel and Coordinator
with a bundled, source-derived execution Host and TUI.

## Architecture

```text
TUI / headless CLI
    -> Host API
    -> KernelHost: domain, intent/authority binding, questions
    -> Coordinator: runs, recursive tasks, shared budget, completion
    -> execution adapters: model gateway, files, shell, MCP
    -> Candidate / Overlay
    -> Python v5 measurement: immutable observations
    -> model assessment + runtime reason + Candidate disposition
```

The Host owns authentication, provider invocation, tool execution and verification.
The TUI requests actions and renders the same Host status as headless execution.
A model assessment, observation or successful tool exit is not legacy Ready.
Set `kernel.executionSemantics` to `legacy` to use the GoalContract, scoped
repair and Python v4 Ready pipeline.

The former minimal `runtime/src` experiment is archived under
`runtime/experiments/minimal-v3`. It is not an alternate product runtime.

## Source execution

Use Bun **1.3.14** and Python **3.11 or newer**. Do not use a virtual environment
whose base Python interpreter has been removed.

Install the verifier into a dedicated environment from the repository root:

```powershell
py -3.12 -m venv .tools/verifier
.tools/verifier/Scripts/python.exe -m pip install -e .
cd runtime
bun install
bun run dev
```

The launcher automatically uses `.tools/bun-1.3.14/bun.exe` and
`.tools/verifier/Scripts/python.exe` when present. On Linux it uses their
`bun` and `bin/python` equivalents. `BASE_HARNESS_PYTHON` may explicitly
select another valid verifier interpreter.

Headless execution uses the same Host:

```powershell
bun run dev -- run "Describe the requested task here"
bun run dev -- --help
```

Use `base-harness.jsonc` for Host configuration. The repository example contains
verification, orchestration and domain defaults but no credentials or assumed
model IDs. The retired experiment's plural `providers` configuration is not
the Host's configuration format.

New ordinary Runs default to `autonomous-v1`. Develop Runs request the existing
edit, shell and task permissions, keep changes in Candidate workspaces, and
apply them only after an explicit admitted `apply_candidate`. Headless exit
codes are 0 for a requested `satisfied` model assessment, 2 for requested
`partial`, `unsolved` or `not_assessed` results, and 1 for runtime failure
or interruption. Structured status keeps the assessment, observations, gates
and runtime reason separate.

## Interaction and authority

- Model selection, authentication and MCP management use the bundled TUI and Host.
- Domain controls include `/develop`, `/general` and `/hackathon`.
- `/plan` prepares one plan-only request; execution requires `/execute`.
- `/goal`, `/verify`, `/evidence` and `/harness` expose Host-owned state.
- Provider reasoning options belong to the selected provider/model capability;
  the Kernel must not guess effort names.
- Autonomous direct and child changes stay in Overlay until an explicit
  Candidate apply rechecks the current grant, exact bytes and baseline.
- Legacy worker changes stay in Overlay until the v4 verifier attests the same
  candidate ID, revision and patch hash.
- A verifier, protocol or isolation failure must not produce Ready.

## Provenance and current validation

Execution and TUI code retain their source provenance and license notices.
Hermes is an architectural reference, not a bundled dependency or a claimed
source transplant. OpenCode and Gajae-Code executables are not required to run
the bundled Host. Optional external execution adapters still require their own
installed programs when explicitly selected.

Restoration is in progress. Source presence is not proof of working OAuth,
live provider access, MCP connectivity or Windows/Linux sandbox containment.
See `docs/RUNTIME_HOST_RESTORATION_2026-09-05.md` for changes and remaining gates.
