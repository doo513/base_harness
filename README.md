# Verified-State Harness

A verified-state agent harness for model-driven software, hackathon, CTF, and controlled tool-use workflows.

```text
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
trusted state / accepted completion
```

The core invariant is:

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or success. Recovery, progress control, context projection, and retrieval admission are kernel-governed and may not bypass those gates.**

Current package version: **v0.9.1**.

## Branches

```text
main
  └─ current integrated user-facing line

develop
  └─ active development / next changes

preprocessing
  └─ frozen pre-integration snapshot

legacy-main-pre-integration
  └─ archived former main tip before integration promotion
```

## What is currently available

```text
Workspace contract
Config + environment secret references
Model Gateway
  ├─ command/local provider
  └─ OpenAI-compatible HTTP provider
Agent plan/task control
Tool contracts + shell/argv execution + bounded workspace reads
MCP stdio tools
Explicit installed Python plugins
Context governance + lexical relevance
Cross-run project/episodic memory
Software profile
Hackathon profile
CTF profile
Verification / completion oracle
Progress / recovery
Persistence / resume
Evaluation / ablation records
CLI
TUI launcher / monitor / inspect
```

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

Linux/macOS shell:

```bash
source .venv/bin/activate
python -m pip install -e .
```

Installed commands:

```text
verified-harness
verified-harness-tui
```

The equivalent module commands are:

```text
python -m harness.cli
python -m harness.tui
```

## Configure a model API

The harness does **not** currently expose its own REST server API. In this repository, "API usage" means configuring the Model Gateway to call an LLM provider API.

Start from the example:

PowerShell:

```powershell
Copy-Item harness.example.toml harness.toml
```

Bash:

```bash
cp harness.example.toml harness.toml
```

Secrets should be environment references, not literal keys committed to TOML.

### Gemini through the OpenAI-compatible endpoint

Set the key:

PowerShell:

```powershell
$env:GEMINI_API_KEY="YOUR_KEY"
```

Bash:

```bash
export GEMINI_API_KEY="YOUR_KEY"
```

Example `harness.toml`:

```toml
profile = "software"
run_dir = "./run"
default_model = "gemini"

[workspace]
root = "."
temp_dir = ".harness-tmp"
build_dir = "build"
cache_dir = ".cache/harness"

[security]
strict_layout = false
strict_tool_isolation = false
network_policy = "allow"
require_sealed_oracle = false

[memory]
enabled = false
root = "../.verified-state-harness-memory"

[models.gemini]
provider = "openai-compatible"
model = "gemini-3.6-flash"
endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key = "env:GEMINI_API_KEY"
timeout_seconds = 120
```

Any provider exposing a compatible `/chat/completions` interface can use the same provider type with its own endpoint/model/key.

## TUI: quickest interactive use

Start a new run:

```powershell
verified-harness-tui new
```

or:

```powershell
python -m harness.tui new
```

For a software task, a typical prompt session is:

```text
Config TOML [harness.toml]: harness.toml
Workspace [.]: C:\work\realtime_ocr
Run directory [./run]: C:\work\harness-runs\ocr-copy-01
Profile (software/hackathon/ctf/demo) [software]: software
Goal: Add a Copy button for each OCR translation result and add tests.
Acceptance commands: enter one per line; blank line finishes.
accept> dotnet test GameOcrTranslator.sln
accept>
Max steps [30]: 30
Execution backend (local/linux-namespace) [local]: local
Network policy (allow/deny) [allow]: allow
Strict workspace/run layout [y/N]: n
Strict tool isolation [y/N]: n
Require sealed completion oracle [y/N]: n
```

During execution the TUI monitors persisted runtime metrics, recent events, recent tool calls, and model/CLI stdout/stderr. Execution still goes through `harness.cli` and the normal Kernel; the TUI does not bypass verification or tool policy.

Resume an existing run:

```powershell
verified-harness-tui resume
```

Inspect a persisted run without executing it:

```powershell
verified-harness-tui inspect C:\work\harness-runs\ocr-copy-01
```

Equivalent module commands:

```text
python -m harness.tui resume
python -m harness.tui inspect <run-dir>
```

## CLI: direct/non-interactive use

Example software run:

```powershell
verified-harness `
  --config harness.toml `
  --profile software `
  --workspace "C:\work\realtime_ocr" `
  --run-dir "C:\work\harness-runs\ocr-copy-01" `
  --goal "Add a Copy button for each OCR translation result and add tests." `
  --accept-command "dotnet test GameOcrTranslator.sln" `
  --max-steps 30
```

The same entrypoint is available as:

```powershell
python -m harness.cli `
  --config harness.toml `
  --profile software `
  --workspace "C:\work\realtime_ocr" `
  --run-dir "C:\work\harness-runs\ocr-copy-01" `
  --goal "Add a Copy button for each OCR translation result and add tests." `
  --accept-command "dotnet test GameOcrTranslator.sln" `
  --max-steps 30
```

Resume uses the same runtime composition plus `--resume` and the same run directory/configuration identity.

## Memory

Cross-run memory is opt-in:

```toml
[memory]
enabled = true
root = "../.verified-state-harness-memory"
project_id = "my-project"
```

The actor can stage evidence-linked memory candidates. Publication occurs only after the run returns. A later run retrieves them as **untrusted project memory**; memory never directly grants trusted truth, progress, or completion.

## MCP and plugins

MCP v1 currently supports **stdio tool discovery/calls**. Example configuration is in `harness.example.toml`.

Important current boundary:

```text
MCP default permission = confirm
TUI interactive persisted approval broker = not implemented yet
```

Python plugins are explicit already-installed trusted host extensions. They are not an isolation mechanism.

## Execution security

For ordinary local development on Windows, use:

```text
execution_backend = local
strict_tool_isolation = false
```

`local` is a convenience execution backend, **not a strong sandbox boundary**.

On a supported Linux host, stronger execution isolation can be requested with:

```text
--execution-backend linux-namespace
--strict-tool-isolation
```

Strict tool isolation fails closed when a selected tool path cannot prove the required isolation. Current host-process MCP/plugin v1 therefore cannot be combined with strict tool isolation.

## Verification / run artifacts

A run persists state and operational evidence under its run directory. Depending on the path exercised, this includes persisted metrics/events/tool-call records and checkpoint/provenance data used for resume and verification.

The model cannot accept its own completion. The normal path remains:

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

## Current limitations

The basic CLI/TUI Software/Hackathon runtime is implemented, but the following are still genuine follow-up areas:

- interactive persisted MCP approval workflow;
- native Anthropic/Gemini adapters and harness-level streaming;
- MCP HTTP/resources/prompts/sampling/elicitation/tasks;
- isolated untrusted plugin runtime;
- semantic/embedding context ranking beyond current lexical relevance;
- memory decay/expiry/global GC and richer multi-writer coordination;
- richer domain semantics and benchmark-tuned progress thresholds;
- repeated real-provider matched benchmarks before any harness-performance claim.

See `docs/tracks/integration-runtime/POST_IMPLEMENTATION_AUDIT.md` for the post-integration gap review.

## Core stage status

| Stage | Scope | Status |
|---|---|---|
| 00 | Research / contracts | HISTORICAL COMPLETE |
| 01 | Truth + execution integrity | HISTORICAL COMPLETE |
| 02 | Capability isolation + sealed oracle | PASS / EXITED + remediation hardening |
| 03 | Persistence + resume + reproducibility | PASS / EXITED (`v0.4.0`) + provenance hardening |
| 04 | Semantic verification | PASS / EXITED (`v0.5.0`) + claim-class hardening |
| 05 | Failure recovery | PASS / EXITED (`v0.6.0`) + controlled effectiveness evidence |
| 06 | Loop / deterministic progress control | PASS / EXITED (`v0.7.0`) + semantic-progress hardening |
| 07 | Context Governance | PASS / EXITED (`v0.8.0`) + trusted-context bounds |
| 08 | Retrieval / Memory Gateway | PASS / EXITED (`v0.9.0`) |

Core Stage 00-08 remains frozen except for confirmed defects. Post-Stage08 product/integration work is tracked under `docs/tracks/` rather than creating Stage 09+.
