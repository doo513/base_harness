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

Current package version: **v0.10.0**.

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

## Conversational TUI

The default TUI is intentionally closer to Claude Code / Antigravity CLI than to a settings dashboard: the terminal transcript is preserved, tasks are typed directly at the prompt, tool/verification/recovery events appear inline, and configuration is opened only through slash commands.

Start inside the project you want to work on:

```bash
cd /path/to/project
verified-harness-tui
```

Or specify the workspace explicitly:

```bash
verified-harness-tui --workspace /path/to/project
```

Example:

```text
╭─ base_harness 0.10.0
│  /home/user/project
│  software · gemini/gemini-3.5-flash · ready
╰─ /help for commands · Ctrl+C interrupts a running task

❯ Add rate limiting to the login API and add regression tests.
  ✻ Working · runs/20260820-151700
  ◇ agent.plan.replaced
  ● workspace.read · ok
  ● argv · ok
  ◆ verification.accepted
  ✓ Completed · steps 9 · tools 4 · runs/20260820-151700

❯
 software │ gemini/gemini-3.5-flash │ ready │ project │ python3 -m pytest -q
```

The bottom status line shows the active mode, model, credential readiness, workspace, and acceptance command. Slash commands are autocompleted while typing.

The TUI displays **operational Harness events only**: plans/status, tool calls, verification, recovery and completion. It does not expose hidden model chain-of-thought.

## Slash commands

```text
/help                    show commands
/status                  current workspace/model/run state
/connect [provider]      connect provider or load a session credential
/model [alias]           show/switch configured model
/mcp list|search|add     MCP discovery/configuration
/skills [query]          search SKILL.md capabilities
/mode [name]             software / hackathon / ctf / demo
/accept [command]        set/reset fixed completion command
/workspace [path]        change project directory
/resume <run-dir>        resume persisted run
/inspect <run-dir>       inspect persisted run
/permissions             show execution/security boundary
/new                     start a fresh conversation marker
/clear                   clear the terminal
/exit                    quit
```

## Provider connection

Connection is deliberately short.

```text
❯ /connect gemini
Model [gemini-3.5-flash]:
API key: ********
  ✓ Connected gemini · gemini-3.5-flash
```

For an already configured provider whose credential is missing, `/connect` asks only for the key. Typing a normal task also detects this condition and asks for the key before the first model call.

A pasted API key is held **only in the current TUI process** and passed to child Harness runs through their process environment. The raw key is not written to `harness.toml`, run artifacts, or a Harness-owned SecretStore.

The config keeps only an environment reference:

```toml
[models.gemini]
provider = "openai-compatible"
model = "gemini-3.5-flash"
endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key = "env:GEMINI_API_KEY"
```

If `GEMINI_API_KEY` already exists in the shell/OS/CI environment, no interactive key entry is required.

Local Ollama does not need an API key:

```text
❯ /connect ollama
Model [qwen2.5-coder:3b]:
```

## Models

```text
❯ /model
Configured models
  ● gemini            gemini-3.5-flash
  ○ local             qwen2.5-coder:3b
Model [gemini]: local
  ✓ Model switched to local · qwen2.5-coder:3b
```

`/models` is retained as an alias for `/model`.

## Task execution

Type the request directly:

```text
❯ Add a Copy button for each OCR translation result and add tests.
```

Every new task receives a fresh run directory such as:

```text
./runs/20260820-151700
```

For common project layouts the TUI detects a basic fixed acceptance command:

```text
Python     python3 -m pytest -q   (Linux/WSL/macOS)
Go         go test ./...
Rust       cargo test
Node       npm test
```

Use `/accept <command>` when the project needs a different completion oracle. If no safe command is detected in software/hackathon mode, the TUI warns that completion may remain unaccepted rather than silently pretending the task succeeded.

During the run the transcript receives compact events:

```text
◇ plan/task event
● tool call
◆ verification event
↻ recovery/strategy event
✕ failure/rejection
✓ accepted completion
```

## MCP and Skills

MCP is available from the same prompt:

```text
/mcp list
/mcp search filesystem
/mcp add
```

Registry search is discovery-only:

```text
search ≠ install
search ≠ enable
search ≠ trust
```

The current runtime integration supports reviewed **stdio MCP** tool discovery/calls. Runtime permission policy still applies after configuration.

Skills are searchable without leaving the session:

```text
/skills
/skills mcp
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
- CLI + conversational TUI
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

The TUI does not weaken these boundaries. A session-pasted API key is process-memory-only and is not persisted by the Harness.

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
