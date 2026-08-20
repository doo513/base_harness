# Verified-State Harness

A verified-state harness for model-driven software, hackathon, CTF, and controlled tool-use workflows.

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

## Branches

```text
main           validated user-facing line
develop        active development
preprocessing  frozen pre-integration snapshot
```

## Install

Python **3.11+** is required.

### Linux / WSL / macOS

Use `python3` explicitly:

```bash
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout main
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

### Windows PowerShell

```powershell
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout main
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Installed commands:

```text
verified-harness
verified-harness-tui
```

### Updating an existing editable install

Linux / WSL / macOS:

```bash
git pull
python3 -m pip install -e .
hash -r
```

Windows PowerShell:

```powershell
git pull
python -m pip install -e .
```

## Visual TUI

Start it from the project you want the Harness to work on:

```bash
verified-harness-tui
```

or point it at another workspace:

```bash
verified-harness-tui /path/to/project
```

The default interaction is prompt-first rather than a setup wizard:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ base_harness  /home/user/project                                    │
│ software · gemini/gemini-3.5-flash · ready                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   What do you want to build or solve?                                │
│   Type a task and press Enter.                                       │
│                                                                      │
│   /connect  /models  /mcp  /skills  /mode  /accept  /help           │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│ acceptance: auto-detect                                              │
└──────────────────────────────────────────────────────────────────────┘
› Add rate limiting to the login API and add regression tests.
```

The TUI uses the same CLI/Kernel runtime underneath; it does not bypass verification, tool permissions, progress control, recovery, or the completion oracle.

### Slash commands

```text
/connect            connect or re-use a model provider
/models             choose a configured model
/mcp                search/configure MCP
/skills [query]     list SKILL.md capabilities
/mode               software / hackathon / ctf / demo
/accept <command>   set the fixed completion command
/workspace <path>   change workspace
/resume <run-dir>   resume a persisted run
/inspect <run-dir>  inspect run state
/new                clear the UI session
/help               show commands
/exit               quit
```

## Provider connection

Run `/connect` inside the TUI.

```text
┌ Connect provider ───────────────────────┐
│ 1. gemini                              │
│ 2. openai                              │
│ 3. openai-compatible                   │
│ 4. ollama                              │
└─────────────────────────────────────────┘
```

For providers that require a key, the TUI offers:

```text
1. use an already exported environment variable
2. paste a key for this TUI session only
3. reference another environment variable
```

Option 2 is the convenient interactive path. The raw key stays only in the current TUI process and is passed to child runs through the process environment; **it is not written to `harness.toml` and is not persisted by a Harness SecretStore**.

The config stores only the reference:

```toml
[models.gemini]
provider = "openai-compatible"
model = "gemini-3.5-flash"
endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key = "env:GEMINI_API_KEY"
```

If you prefer persistent shell/OS/CI credential management, export the variable outside the Harness and choose option 1.

Local Ollama requires no API key:

```text
/connect → ollama
```

## Models

Use `/models` to choose among configured model aliases. The selected alias becomes `default_model` in `harness.toml`.

## Task execution

For a normal software project, type the task directly:

```text
› Add a Copy button for each OCR translation result and add tests.
```

The TUI automatically creates a fresh run directory such as:

```text
./runs/20260820-110500
```

For common project layouts it also detects a basic fixed acceptance command:

```text
Python     python3 -m pytest -q   (Linux/WSL/macOS)
Go         go test ./...
Rust       cargo test
Node       npm test
```

If no safe default is detected in `software` or `hackathon` mode, the TUI asks for one completion command before the run starts. Use `/accept` to set it in advance.

During execution the screen shows the current run, step count, tool calls, failures, recovery transitions, recent events, and recent stdout/stderr.

## MCP and Skills

Use:

```text
/mcp
/skills
```

`/mcp` can search the official MCP Registry and configure a reviewed **stdio** MCP server. Search is discovery-only:

```text
search ≠ install
search ≠ enable
search ≠ trust
```

Bundled Skill actions include:

```text
connect-provider
mcp-search
configure-mcp
```

Workspace-local skills can be placed under:

```text
<workspace>/.harness/skills/<skill-name>/SKILL.md
```

Custom Markdown skills do not gain arbitrary execution authority. Tool authority remains with the Harness runtime.

## CLI

The non-interactive CLI remains available.

Linux / WSL / macOS example:

```bash
verified-harness \
  --config harness.toml \
  --profile software \
  --workspace "$PWD" \
  --run-dir ./runs/rate-limit-01 \
  --goal "Add rate limiting to the login API and add regression tests." \
  --accept-command "python3 -m pytest -q" \
  --max-steps 30
```

Resume an existing run:

```bash
verified-harness --config harness.toml --run-dir ./runs/rate-limit-01 --resume
```

A new run must use a new/empty run directory; a conflict is reported as an actionable CLI error rather than a Python traceback.

## Current runtime surface

- Workspace contract
- typed TOML config + environment secret references
- Model Gateway: command/local + OpenAI-compatible HTTP
- LLMController / agent control
- shell/argv execution + bounded workspace reads
- MCP stdio tool discovery/calls
- explicit Python plugins
- context governance + lexical relevance
- cross-run project memory
- software / hackathon / CTF / demo profiles
- verification + completion oracle
- deterministic progress control + recovery
- persistence / resume / evaluation records
- CLI + visual task-first TUI
- SKILL.md connection/discovery catalog

## Security boundaries

```text
Model / Skill output
        ↓
proposal only
        ↓
Harness Tool Runtime / permission gate
        ↓
evidence
        ↓
Verifier / Completion Oracle
```

The visual TUI does not weaken these boundaries. A session-pasted API key is process-memory-only and is never placed in run artifacts or TOML by the TUI.

For ordinary local development, `execution_backend=local` is a convenience backend, not a strong sandbox. On supported Linux systems, stronger execution isolation can be requested with `linux-namespace` and strict tool isolation.

## Current limitations

- no general authenticated problem-site intake orchestrator yet;
- no persistent interactive MCP approval broker;
- MCP runtime is currently primarily stdio `tools/list` + `tools/call`;
- no isolated untrusted plugin runtime;
- context relevance is still primarily lexical;
- project memory still needs richer decay/GC/multi-writer coordination;
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
