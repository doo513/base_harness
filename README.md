# Verified-State Harness

A model-driven task harness that lets an actor plan and use tools while the Harness keeps authority over workspace boundaries, evidence, verification, recovery, and accepted completion.

```text
User request
    ↓
Task intake
    ↓
Actor plan / checklist
    ↓
Tools + evidence
    ↓
Verified-State Kernel
  ├─ workspace boundary
  ├─ capability / tool authority
  ├─ verification
  ├─ progress control
  ├─ recovery
  └─ completion oracle
    ↓
Final result + persisted evidence
```

Core invariant:

> **The actor may propose and act; only Harness-side verification/oracles may promote trusted truth or accepted completion.**

Current package version: **0.10.0**.

Detailed evidence/causal history of the latest integration work:

- [`docs/tracks/integration-runtime/RECENT_EVOLUTION_EVIDENCE_REPORT_2026-08-20.md`](docs/tracks/integration-runtime/RECENT_EVOLUTION_EVIDENCE_REPORT_2026-08-20.md)

---

# 1. Installation

Python **3.11+** is required.

## Linux / WSL / macOS

```bash
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout main

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Check the installed commands:

```bash
verified-harness --help
verified-harness-tui --help
```

## Windows PowerShell

```powershell
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout main

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Check:

```powershell
verified-harness --help
verified-harness-tui --help
```

## Updating an existing install

Linux / WSL / macOS:

```bash
cd /path/to/base_harness
git pull
source .venv/bin/activate
python3 -m pip install -e .
hash -r
```

Windows PowerShell:

```powershell
cd C:\path\to\base_harness
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

If you installed the project into another virtual environment, activate that environment instead.

---

# 2. How to start the Harness

There are two entry points.

## Recommended: conversational TUI

```bash
verified-harness-tui
```

This is the normal interactive interface.

```text
╭─ base_harness 0.10.0
│  /current/project
│  software · gemini/gemini-3.5-flash · ready
╰─ /help for commands · Ctrl+C interrupts a running task

  Tell me what you want done. I’ll plan the work, use the available tools, and verify the result.

❯
```

Type the request directly. You normally do **not** need to select a Skill first.

## Non-interactive CLI

```bash
verified-harness --help
```

Use this for scripts, CI, reproducible experiments, or when all run parameters should be explicit.

---

# 3. Recommended daily-use patterns

## Pattern A — run inside the target project

```bash
cd /path/to/my-project
verified-harness-tui
```

Then type:

```text
❯ 로그인 API에 rate limit 추가하고 회귀 테스트까지 해줘
```

The current directory is initially the workspace.

If no model is configured, use `/connect` once in the session.

## Pattern B — specify the target workspace when starting

```bash
verified-harness-tui --workspace /path/to/my-project
```

WSL example:

```bash
verified-harness-tui --workspace /mnt/c/Users/me/Downloads/realtime_ocr
```

## Pattern C — reuse one shared Harness config

By default the TUI uses `harness.toml` from the shell working directory.

If you prefer one shared provider/model configuration, point at it explicitly:

```bash
verified-harness-tui \
  --config /path/to/base_harness/harness.toml \
  --workspace /path/to/my-project
```

WSL example:

```bash
verified-harness-tui \
  --config /mnt/c/Users/me/Downloads/base_harness/harness.toml \
  --workspace /mnt/c/Users/me/Downloads/realtime_ocr
```

This lets model/provider configuration be reused across projects without copying the TOML file into every project.

---

# 4. Connecting a model

Connection is a control operation, not the main task workflow.

Inside the TUI:

```text
/connect gemini
/connect openai
/connect ollama
/connect openai-compatible
```

## Gemini

```text
❯ /connect gemini
Model [gemini-3.5-flash]:
API key: ********
```

The TUI stores model/provider configuration in TOML, but the **raw API key is not written to the TOML**.

Example persisted config:

```toml
[models.gemini]
provider = "openai-compatible"
model = "gemini-3.5-flash"
endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key = "env:GEMINI_API_KEY"
```

A key pasted interactively is held only in the current TUI process.

If you want the credential to survive TUI restarts, keep it in your OS/shell/CI secret mechanism and let the TOML reference the environment variable. The Harness intentionally does not own a persistent SecretStore.

## Ollama / local model

Make sure Ollama is already running, then:

```text
❯ /connect ollama
Model [qwen2.5-coder:3b]:
```

Default local endpoint:

```text
http://127.0.0.1:11434/v1/
```

No API key is required for the default local route.

## Other providers / new models

If the service supports the OpenAI-compatible `chat/completions` protocol:

```text
❯ /connect openai-compatible
Model: provider/model-name
Endpoint: https://provider.example.com/v1/
API key: ********
```

This is the current generic connection path for providers that do not have a built-in preset.

## Switching configured models

```text
/model
```

or:

```text
/model <alias>
```

`/models` is retained as an alias.

---

# 5. Normal task usage

The normal interface is the natural-language request.

Examples:

```text
❯ 로그인 API에 rate limit 추가하고 테스트해줘

❯ 이 에러 원인을 찾아서 수정하고 회귀 테스트까지 해줘

❯ 프로젝트 구조를 확인하고 잘못된 의존성을 정리해줘

❯ 이 CTF 문제 파일들을 분석해서 풀이를 진행해줘
```

The intended internal flow is:

```text
request
  ↓
actor analyzes task
  ↓
actor creates plan/checklist
  ↓
actor uses tools
  ↓
Harness records evidence
  ↓
actor compares work against plan
  ↓
actor repairs gaps
  ↓
completion request
  ↓
Harness oracle accepts/rejects
```

The plan is actor bookkeeping. It does not itself become trusted truth.

---

# 6. Project analysis / report usage

You do **not** need to switch to a separate Research mode.

Example:

```text
❯ 이 프로젝트를 분석해서 딥한 보고서 써줘
```

The Harness keeps the selected profile and attaches a task-specific evidence-backed artifact contract.

Default output:

```text
PROJECT_ANALYSIS_REPORT.md
```

You can request another Markdown filename:

```text
❯ 프로젝트 구조를 분석해서 architecture_review.md 보고서로 작성해줘
```

The analysis workflow is guided toward:

```text
plan/checklist
  ↓
project inventory
  ↓
relevant docs/config/source/tests
  ↓
direct workspace evidence
  ↓
analysis against checklist
  ↓
write requested artifact
  ↓
re-read / recheck
  ↓
completion oracle
```

The report completion gate requires at least:

- the artifact stays inside the workspace;
- successful workspace evidence exists;
- at least one actual source-file read occurred;
- the requested artifact exists;
- it contains non-trivial content.

This prevents a report from being accepted without first inspecting the project. It does not yet prove every natural-language statement in the report individually.

---

# 7. Supplying a project path in the request

The workspace is a security boundary.

During a run, the LLM cannot arbitrarily change it.

```text
WorkspaceContract.root
       ↓
file.read / file.search / directory.list
       ↓
relative paths inside root only
```

The conversational TUI has a **pre-runtime task-intake** step.

If the user explicitly supplies exactly one existing project directory, that directory may be selected as the workspace **before** the runtime starts.

Example from WSL:

```text
❯ "C:\Users\me\Downloads\realtime_ocr" 분석해서 딥한 보고서 써줘
```

The TUI can map the Windows drive path to:

```text
/mnt/c/Users/me/Downloads/realtime_ocr
```

and then construct the normal `WorkspaceContract` around that directory.

If more than one existing project path is present, the TUI does not guess which directory should become the write target.

Use:

```text
/workspace /path/to/project
```

when an explicit override is needed.

---

# 8. What appears while a task runs

The conversational UI hides low-value internal persistence noise and shows operational events.

```text
◇ Plan     actor plan/checklist update
● Tool     tool execution
✓ Verify   accepted verification
↻ Retry    recovery/strategy action
✕ Issue    meaningful failure
✓ Final    completion-oracle result
```

Hidden model chain-of-thought is not displayed.

Example:

```text
❯ 프로젝트 분석해서 보고서 써줘

  ◇ Plan   map project structure and identify core flow
  ● Tool   directory.list
  ● Tool   file.read
  ● Tool   file.read
  ✓ Final  requested artifact exists and was produced after workspace evidence collection

  ✓ Finished
  Evidence  12 workspace observations · 2 verified facts
  Output    /path/to/project/PROJECT_ANALYSIS_REPORT.md
  Run files /path/to/launcher/runs/20260820-...
```

---

# 9. Run files and outputs

Every new task uses a fresh run directory.

Typical layout:

```text
runs/20260820-164000/
├─ run_manifest.json
├─ checkpoint.json
├─ events.jsonl
├─ tool_calls.jsonl
├─ metrics.json
├─ artifacts/
├─ receipts/
└─ final_result.json
```

`final_result.json` is the compact deterministic result projection for the UI and later inspection.

It includes:

- accepted completion status;
- workspace;
- step count;
- evidence counts/refs;
- verified facts;
- recent failures;
- requested artifact path/hash/size when applicable.

A requested analysis report itself is written into the target workspace, while the Harness run/audit files remain in the run directory.

---

# 10. Resume and inspect

## Inspect a run

```text
/inspect ./runs/20260820-164000
```

## Resume a persisted run

```text
/resume ./runs/20260820-164000
```

A new run must use an empty/fresh run directory. The CLI reports a useful error rather than overwriting an existing persisted run.

CLI resume:

```bash
verified-harness \
  --config harness.toml \
  --run-dir ./runs/20260820-164000 \
  --resume
```

---

# 11. Slash commands

Slash commands are controls and overrides. They are not required before every task.

```text
/help                    show commands
/status                  current workspace/model/run state
/connect [provider]      connect provider / load session credential
/model [alias]           show or switch model
/mcp list|search|add     MCP discovery/configuration
/skills [query]          inspect available SKILL.md capabilities
/mode [name]             explicit profile override
/accept [command]        explicit command-completion override
/workspace [path]        explicit workspace override
/resume <run-dir>        resume persisted run
/inspect <run-dir>       inspect persisted run
/permissions             show security/execution boundary
/new                     new conversation marker
/clear                   clear terminal
/exit                    exit
```

---

# 12. MCP and Skills

## MCP

```text
/mcp list
/mcp search filesystem
/mcp add
```

MCP Registry search is discovery-only:

```text
search ≠ install
search ≠ enable
search ≠ trust
```

The current runtime path supports reviewed **stdio MCP** tool discovery/calls.

Do not assume HTTP MCP execution is implemented merely because a remote server exists.

## Skills

```text
/skills
/skills mcp
```

Bundled/workspace skills are reusable guidance and capability metadata.

Normal users do not need to pick a Skill for every request. The actor is expected to analyze the task and use available capabilities as needed.

Workspace-local Skill location:

```text
<workspace>/.harness/skills/<skill-name>/SKILL.md
```

A custom Markdown Skill does not receive arbitrary tool authority. Runtime permissions still apply.

---

# 13. Explicit CLI examples

## Software development

Linux / WSL / macOS:

```bash
verified-harness \
  --config /path/to/harness.toml \
  --profile software \
  --workspace /path/to/project \
  --run-dir ./runs/rate-limit-01 \
  --goal "Add rate limiting to the login API and add regression tests." \
  --accept-command "python3 -m pytest -q" \
  --max-steps 30
```

## Evidence-backed project report

```bash
verified-harness \
  --config /path/to/harness.toml \
  --profile software \
  --workspace /path/to/project \
  --run-dir ./runs/project-analysis-01 \
  --goal "Analyze this project and produce a deep architecture report." \
  --artifact-target PROJECT_ANALYSIS_REPORT.md \
  --max-steps 30
```

## CTF profile

```bash
verified-harness \
  --config /path/to/harness.toml \
  --profile ctf \
  --workspace /path/to/challenge \
  --run-dir ./runs/ctf-01 \
  --goal "Analyze the challenge and solve it." \
  --max-steps 30
```

---

# 14. Architecture placement

Recent usability changes were deliberately placed around the existing kernel.

```text
Conversational TUI
      ↓
Task Intake
      ↓
Profile + optional task contract
      ↓
existing CLI composition
      ↓
Model Gateway / LLMController
      ↓
Verified-State Kernel
      ↓
FinalResult presenter
```

The task-intake and evidence-backed deliverable work does not grant the LLM new filesystem, verification, or completion authority.

Recent evidence report:

- [`RECENT_EVOLUTION_EVIDENCE_REPORT_2026-08-20.md`](docs/tracks/integration-runtime/RECENT_EVOLUTION_EVIDENCE_REPORT_2026-08-20.md)

---

# 15. Current runtime surface

- `WorkspaceContract` actor boundary
- bounded pre-runtime task intake for explicit user paths
- typed TOML config + environment-secret references
- Model Gateway: command/local + OpenAI-compatible HTTP
- LLMController + persistent actor plan/task bookkeeping
- bounded workspace reads
- shell/argv execution through Tool Runtime
- stdio MCP discovery/calls
- explicit Python plugins
- Context Governance + relevance selection
- cross-run project memory
- software / hackathon / CTF / demo profiles
- task-specific evidence-backed artifact composition
- verification and completion oracles
- deterministic progress control + recovery
- persistence/resume
- deterministic `final_result.json`
- conversational terminal UI

---

# 16. Security boundaries

```text
User request
    ↓
Task intake may select only an explicit existing project path
    ↓
WorkspaceContract is fixed
    ↓
Model output = proposal/action request
    ↓
Harness permission / Tool Runtime
    ↓
Evidence
    ↓
Verifier / Completion Oracle
```

Important points:

- API keys pasted into TUI are not written raw to `harness.toml`;
- the LLM cannot expand its own workspace root;
- multiple detected project directories are not guessed;
- Skills do not bypass Tool Runtime permissions;
- MCP Registry search does not imply trust or activation;
- model completion text is not accepted as proof of task success.

For ordinary local development, `execution_backend=local` is a convenience backend rather than a strong OS sandbox. Supported Linux environments can use the stronger namespace/isolation options when needed.

---

# 17. Current limitations

- no general authenticated problem-site intake orchestrator;
- no persistent Harness-owned SecretStore by design;
- no persistent interactive MCP approval broker;
- MCP execution is currently primarily stdio;
- no isolated untrusted plugin runtime;
- context relevance remains primarily lexical;
- project memory still needs richer decay/GC/multi-writer coordination;
- report completion proves evidence collection + deliverable existence, not semantic correctness of every sentence;
- local-provider endpoint self-healing/WSL gateway fallback is not yet implemented;
- generic OpenAI-compatible provider registration can be made more convenient for many custom aliases;
- stronger repeated live-model E2E benchmarks are still required before claiming general task-performance gains.

---

# 18. Validation status

Latest validated source before this README/report update:

```text
9406f3bddff8477e95b63025f14effda49a7348d
```

CI evidence:

```text
292 passed
7 skipped
```

with CLI/TUI entry points, core freeze audit, and Stage 02–08 regression/probe gates passing.

See:

- [`docs/tracks/integration-runtime/CI_STATUS.md`](docs/tracks/integration-runtime/CI_STATUS.md)

---

# 19. Branches

```text
main           validated user-facing line
develop        active development
preprocessing  frozen pre-integration snapshot
```
