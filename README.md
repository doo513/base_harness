# Verified-State Harness

A verified-state agent harness for model-driven software, hackathon, CTF, and controlled tool-use workflows.

```text
Task / Workspace
      ↓
Model / Agent
      ↓ proposes / acts
Verified-State Kernel
  ├─ Context Governance
  ├─ Capability / Tool Runtime
  ├─ Verification
  ├─ Progress Control
  ├─ Recovery
  └─ Completion Oracle
      ↓
verified run state / accepted completion
```

Core invariant:

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success.**

Current package version: **v0.9.1**.

## Branches

```text
main           validated user-facing line
develop        active development
preprocessing  frozen pre-integration snapshot
```

## Current runtime surface

- Workspace contract
- typed TOML config + environment secret references
- Model Gateway: command/local + OpenAI-compatible HTTP
- LLMController / agent control
- tool contracts, shell/argv execution, bounded workspace reads
- MCP stdio tool discovery/calls
- explicit Python plugins
- context governance + lexical relevance
- cross-run project memory
- software / hackathon / CTF / demo profiles
- verification, completion oracle, progress control, recovery
- persistence / resume / evaluation records
- CLI
- **task-first TUI**
- **SKILL.md catalog for connection/discovery workflows**

## Install

Python **3.11+** is required.

```bash
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout main
python -m venv .venv
```

PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Linux/macOS/WSL:

```bash
source .venv/bin/activate
python -m pip install -e .
```

Commands:

```text
verified-harness
verified-harness-tui
```

### Updating an existing editable install

After pulling a newer `main`, refresh the editable install so new or changed console entry points are regenerated:

```bash
git pull
python -m pip install -e .
```

If `verified-harness-tui` is missing or appears stale, verify the module directly:

```bash
python -m harness.tui
```

Then reinstall with `python -m pip install -e .`.

## Recommended use: task-first TUI

Run without arguments:

```powershell
verified-harness-tui
```

Home:

```text
Verified-State Harness
  1. New task
  2. Skills / connections
  3. Resume run
  4. Inspect run
  q. Quit
```

A normal development run starts with the task, not provider settings:

```text
Workspace [.]: C:\work\my-project
Task / problem: Add rate limiting to the login API and add regression tests.
Mode (software/hackathon/ctf/demo) [software]: software
Config TOML [harness.toml]: harness.toml
Run directory [runs\20260820-105300]:
Acceptance commands:
accept> pytest -q
accept>
Advanced execution settings [y/N]: n
```

For **New task**, the TUI proposes a fresh timestamped directory under `./runs/`. It will not reuse a non-empty run directory. Use **Resume run** when you want to continue an existing persisted run.

Hackathon example:

```text
Workspace [.]: C:\hackathon\prototype
Task / problem: Implement the demo API from the requirements, wire the frontend, and verify the demo path.
Mode [software]: hackathon
```

The TUI translates this into the normal CLI/runtime boundary. It does not bypass Kernel verification, tool permissions, recovery, or completion rules.

Direct subcommands remain available:

```text
verified-harness-tui new
verified-harness-tui resume
verified-harness-tui inspect <run-dir>
```

## Skills: connections and discovery

Connection/discovery UX is intentionally separated from the main task flow.

Bundled skills use an Agent-Skills-style `SKILL.md` structure. The catalog loads lightweight metadata first and reads the full skill only when selected.

List skills:

```powershell
verified-harness-tui skills
```

Search skills:

```powershell
verified-harness-tui skills mcp
```

Current built-ins:

```text
connect-provider  configure an LLM route
mcp-search        search the official MCP Registry
configure-mcp     add an explicit reviewed MCP connection
```

### Connect a model provider

```powershell
verified-harness-tui skill connect-provider --config harness.toml
```

Example:

```text
Provider (gemini/openai/openai-compatible/ollama) [gemini]: gemini
Model alias [gemini]: gemini
Model [gemini-3.5-flash]:
Endpoint [...]:
API-key environment variable [GEMINI_API_KEY]:
Use this as default model [Y/n]: y
```

The skill writes only configuration and a secret reference:

```toml
default_model = "gemini"

[models.gemini]
provider = "openai-compatible"
model = "gemini-3.5-flash"
endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key = "env:GEMINI_API_KEY"
timeout_seconds = 120
```

**Raw API keys are not written to `harness.toml`.** Secret values stay in the OS/shell/CI/external secret system; the Harness only resolves `env:NAME` at runtime.

This is deliberate: the Harness does not implement its own persistent SecretStore.

### Search MCP servers

```powershell
verified-harness-tui skill mcp-search
```

`mcp-search` queries the **official MCP Registry** and displays metadata such as name, version, description, repository and package/remote hints.

Discovery is read-only:

```text
search ≠ install
search ≠ enable
search ≠ trust
```

After reviewing a server, configure it explicitly:

```powershell
verified-harness-tui skill configure-mcp --config harness.toml
```

For stdio MCP servers, the skill stores argv as an array rather than a shell string. MCP credentials are also stored only as environment references.

### Skill security boundary

`SKILL.md` does **not** get arbitrary execution authority.

```text
Bundled Skill metadata
      ↓
whitelisted Harness action
      ↓
config/discovery operation

Custom Skill
      ↓
search / display only
```

A custom skill cannot become an executable plugin merely by placing commands in Markdown. Tool authority remains with the existing Harness runtime.

Additional user skills can be placed under:

```text
<workspace>/.harness/skills/<skill-name>/SKILL.md
```

or referenced with `HARNESS_SKILLS_DIR`.

## Orchestration path

The current connected path is:

```text
Workspace + Task + Mode
        ↓
TUI
        ↓
Config / selected model / explicit MCP & plugins
        ↓
CLI composition
        ↓
Model Gateway → LLMController
        ↓
Tool Runtime / MCP / Plugin tools
        ↓
Evidence → Verification → Progress / Recovery
        ↓
Completion Oracle
        ↓
run_dir artifacts + result state
```

This means **development and hackathon folder-based workflows are connected end-to-end**.

Not implemented yet:

```text
problem-site URL
      ↓
automatic authenticated site/file intake
      ↓
automatic workspace construction
```

A site URL can currently be included in the task/context only if the required access/tooling already exists; there is not yet a general site-intake adapter.

## CLI: non-interactive use

Example:

```powershell
verified-harness `
  --config harness.toml `
  --profile software `
  --workspace "C:\work\my-project" `
  --run-dir ".\runs\rate-limit-01" `
  --goal "Add rate limiting to the login API and add regression tests." `
  --accept-command "pytest -q" `
  --max-steps 30
```

A **new** CLI run requires an empty/new `--run-dir`. To continue an existing run instead:

```powershell
verified-harness --config harness.toml --run-dir ".\runs\rate-limit-01" --resume
```

If a new run points at a non-empty directory, the CLI exits with an actionable message instead of a Python traceback.

## Memory

Cross-run memory is opt-in:

```toml
[memory]
enabled = true
root = "../.verified-state-harness-memory"
project_id = "my-project"
```

Retrieved project memory is treated as untrusted context; it cannot directly grant trusted truth, progress, or completion.

## MCP and plugins

Current MCP runtime support is primarily **stdio tools/list + tools/call**.

Important boundary:

```text
MCP default permission = confirm
interactive persisted MCP approval broker = not implemented yet
```

Python plugins are explicit already-installed host extensions and are not an isolation mechanism.

## Execution security

For ordinary local development:

```text
execution_backend = local
strict_tool_isolation = false
```

`local` is a convenience backend, not a strong sandbox boundary.

On a supported Linux host:

```text
--execution-backend linux-namespace
--strict-tool-isolation
```

Strict tool isolation fails closed when a selected tool path cannot prove the required isolation. Current host-process MCP/plugin v1 cannot be combined with strict tool isolation.

## Verification and run artifacts

Runs persist operational state under `run_dir`, including the relevant metrics/events/tool records and checkpoint/provenance artifacts used by the active path.

```text
Actor work
  ↓
Tool / evidence
  ↓
Verifier-backed facts
  ↓
Progress
  ↓
Completion request
  ↓
Harness-side completion oracle
  ↓
accepted / rejected
```

The model cannot accept its own completion.

## Current limitations

- no general problem-site / authenticated intake orchestrator yet;
- no persistent interactive MCP approval broker;
- no native Anthropic/Gemini adapter or harness-level streaming;
- MCP HTTP/resources/prompts/sampling/elicitation/tasks are not fully integrated;
- no isolated untrusted plugin runtime;
- context relevance is still primarily lexical;
- project memory lacks richer decay/GC/multi-writer coordination;
- progress thresholds still need representative-corpus tuning;
- repeated matched real-provider benchmarks are still required before claiming general performance gains.

## Core stage status

| Stage | Scope | Status |
|---|---|---|
| 00 | Research / contracts | HISTORICAL COMPLETE |
| 01 | Truth + execution integrity | HISTORICAL COMPLETE |
| 02 | Capability isolation + sealed oracle | PASS / EXITED |
| 03 | Persistence + resume + reproducibility | PASS / EXITED |
| 04 | Semantic verification | PASS / EXITED |
| 05 | Failure recovery | PASS / EXITED |
| 06 | Deterministic progress control | PASS / EXITED |
| 07 | Context Governance | PASS / EXITED |
| 08 | Retrieval / Memory Gateway | PASS / EXITED |

Core Stage 00-08 remains frozen except for confirmed defects. Product/integration work is layered above the Kernel rather than creating Stage 09+.
