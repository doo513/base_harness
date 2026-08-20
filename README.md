# Verified-State Harness

A verified-state harness for model-driven development, project analysis, hackathon, CTF, and controlled tool-use workflows.

```text
User request
    ↓
Task intake
    ↓
Actor plans / acts
    ↓
Verified-State Kernel
  ├─ Workspace boundary
  ├─ Context governance
  ├─ Capability / Tool runtime
  ├─ Verification
  ├─ Progress control
  ├─ Recovery
  └─ Completion oracle
    ↓
Evidence-backed result
```

Core invariant:

> **Actor output may propose and act; only harness-side verification/oracles may promote trusted truth or accepted completion.**

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

After pulling a newer `main`:

```bash
git pull
python3 -m pip install -e .   # Linux / WSL / macOS
hash -r
```

Installed commands:

```text
verified-harness
verified-harness-tui
```

## Recommended use

Run the conversational TUI and type the task directly.

```bash
verified-harness-tui
```

Example development request:

```text
❯ 로그인 API에 rate limit 추가하고 회귀 테스트까지 해줘
```

Example project-analysis request:

```text
❯ "C:\Users\me\Downloads\realtime_ocr" 분석해서 딥한 보고서 써줘
```

The user normally does **not** need to choose a skill or a special research mode.

The intended path is:

```text
request
  ↓
understand target / deliverable
  ↓
actor creates a checklist / plan
  ↓
use tools and collect evidence
  ↓
work while rechecking the plan
  ↓
verify completion contract
  ↓
show result + persisted evidence
```

## Workspace model

The workspace is a security boundary, not an LLM preference.

`WorkspaceContract.root` is fixed **before** a run starts. File tools accept only relative paths that remain inside that root. The actor cannot change the workspace while the Kernel is running.

```text
WorkspaceContract.root
        ↓
file.read
file.search
 directory.list
shell / argv execution workspace
        ↓
paths must remain inside root
```

### Explicit path in a user request

The conversational TUI has a bounded task-intake step.

If the request contains exactly one explicit directory that exists locally, the TUI uses that user-supplied directory as the workspace **before** constructing the runtime.

```text
❯ "C:\Users\me\Downloads\realtime_ocr" 분석해서 보고서 써줘

  ✓ Using the project you requested · /mnt/c/Users/me/Downloads/realtime_ocr
```

On WSL, a Windows drive path can be mapped to the corresponding `/mnt/<drive>/...` location.

If more than one existing directory is present, the TUI does not guess which one is the write target. Use:

```text
/workspace <path>
```

This preserves the original security design: **the LLM does not gain authority to expand its own filesystem scope.**

## Plans and task execution

The actor already has persistent planning/task bookkeeping:

```text
plan
  ├─ objective
  └─ checklist tasks
```

That plan is guidance only. It does not become trusted truth or completion authority.

The expected behavior is:

1. analyze the request;
2. create a concrete checklist/plan;
3. inspect the target and gather evidence;
4. execute the work;
5. compare progress/result with the original checklist;
6. correct gaps;
7. request completion;
8. let the Harness oracle accept/reject it.

## Evidence-backed report / document tasks

There is **no automatic Research profile switch**.

When the user explicitly asks for a report/document deliverable, task intake attaches an **evidence-backed artifact contract** to the currently selected profile.

For example:

```text
❯ 이 프로젝트 구조를 분석해서 딥한 보고서 써줘
```

is treated as:

```text
current profile/tools/security
        +
evidence-backed artifact task contract
```

rather than:

```text
software → automatically replace with research mode
```

Default report artifact:

```text
PROJECT_ANALYSIS_REPORT.md
```

An explicit Markdown filename in the request is preserved:

```text
❯ 프로젝트 분석해서 architecture_review.md 보고서 작성해줘
```

### Artifact workflow

The Harness provides task workflow guidance roughly equivalent to:

```text
Plan/checklist
   ↓
Inspect project structure
   ↓
Read relevant source/config/docs/tests
   ↓
Collect workspace evidence
   ↓
Analyze gaps against checklist
   ↓
Write requested artifact
   ↓
Re-read and recheck artifact
   ↓
Completion oracle
```

The artifact completion oracle requires at minimum:

- the requested artifact must remain inside the workspace;
- direct workspace evidence must have been collected first;
- at least one source file must have been read;
- the artifact must exist and contain non-trivial content.

This does not claim that every sentence is mathematically proven. It prevents the weaker failure mode where the actor writes a report without inspecting the target project at all.

## Final result

Each completed or exhausted run persists:

```text
<run-dir>/final_result.json
```

It records deterministic result metadata such as:

- accepted completion status;
- workspace;
- requested deliverable metadata/hash when applicable;
- number of workspace evidence observations;
- registered evidence refs;
- verified facts;
- recent failure records.

The TUI renders a compact user-facing result instead of requiring the user to inspect `events.jsonl` manually.

Example:

```text
  ✓ Finished
  Evidence  14 workspace observations · 3 verified facts
  Output    /mnt/c/.../realtime_ocr/PROJECT_ANALYSIS_REPORT.md
  Preview
    │ # Realtime OCR Project Analysis
    │ ## Architecture
    │ ...
  Run files  /.../runs/20260820-...
```

If completion fails, the TUI shows the last meaningful failure reason and the persisted run directory.

Low-value internal events such as repeated `state.snapshot` records are not printed in the normal conversation transcript.

## Conversational TUI

The default interface is prompt-first, closer to terminal coding agents than to a settings dashboard.

```text
╭─ base_harness 0.10.0
│  /home/user/project
│  software · gemini/gemini-3.5-flash · ready
╰─ /help for commands · Ctrl+C interrupts a running task

  Tell me what you want done. I’ll plan the work, use the available tools, and verify the result.
  You normally do not need to choose a skill or task mode manually.

❯
```

Operational events are shown inline:

```text
◇ Plan    actor plan/checklist
● Tool    tool use
✓ Verify  accepted verification
↻ Retry   recovery
✕ Issue   meaningful failure message
✓ Final   completion oracle result
```

Hidden chain-of-thought is not displayed.

## Slash commands

Slash commands are controls/overrides, not the normal task interface.

```text
/help                    show commands
/status                  current workspace/model/run state
/connect [provider]      connect provider or load a session credential
/model [alias]           show/switch configured model
/mcp list|search|add     MCP discovery/configuration
/skills [query]          inspect SKILL.md capabilities
/mode [name]             explicit profile override
/accept [command]        explicit command-completion override
/workspace [path]        explicit workspace override
/resume <run-dir>        resume persisted run
/inspect <run-dir>       inspect persisted run
/permissions             show execution/security boundary
/new                     fresh conversation marker
/clear                   clear terminal
/exit                    quit
```

## Provider connection

```text
❯ /connect gemini
Model [gemini-3.5-flash]:
API key: ********
  ✓ Connected gemini · gemini-3.5-flash
```

A pasted API key is held only in the current TUI process. The Harness writes only a reference such as:

```toml
[models.gemini]
provider = "openai-compatible"
model = "gemini-3.5-flash"
endpoint = "https://generativelanguage.googleapis.com/v1beta/openai/"
api_key = "env:GEMINI_API_KEY"
```

The Harness does not implement a persistent SecretStore.

Local Ollama requires no API key:

```text
/connect ollama
```

For a provider/model that is not in the presets, use the OpenAI-compatible connection path when the endpoint implements that protocol.

## MCP and Skills

```text
/mcp list
/mcp search filesystem
/mcp add
/skills
```

MCP Registry search is discovery-only:

```text
search ≠ install
search ≠ enable
search ≠ trust
```

Current MCP runtime integration is primarily reviewed stdio `tools/list` + `tools/call`.

Skills remain reusable guidance/discovery units. They are not intended to be something the user must manually select before every normal task.

Custom Markdown skills do not gain arbitrary execution authority.

Workspace-local skills:

```text
<workspace>/.harness/skills/<skill-name>/SKILL.md
```

## CLI

The non-interactive CLI remains available.

Development example:

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

Evidence-backed artifact example:

```bash
verified-harness \
  --config harness.toml \
  --profile software \
  --workspace "$PWD" \
  --run-dir ./runs/analysis-01 \
  --goal "Analyze this project and produce a deep report." \
  --artifact-target PROJECT_ANALYSIS_REPORT.md \
  --max-steps 30
```

A new run requires a new/empty run directory. Use `--resume` for an existing persisted run.

## Architectural placement

The new task-intake/artifact behavior is deliberately outside the frozen Kernel:

```text
TUI / Task Intake
    ↓
Task-specific profile composition
    ↓
existing CLI composition
    ↓
existing Model Gateway / Controller
    ↓
existing Tool Runtime
    ↓
existing verification / progress / recovery
    ↓
task-specific completion oracle
    ↓
FinalResult presenter
```

No Stage 09 was created and the Stage 00–08 Kernel contracts remain unchanged.

## Current runtime surface

- Workspace contract
- bounded task intake for explicit user paths
- typed TOML config + environment secret references
- Model Gateway: command/local + OpenAI-compatible HTTP
- LLMController / actor plan/task control
- shell/argv execution + bounded workspace reads
- MCP stdio tool discovery/calls
- explicit Python plugins
- context governance + lexical relevance
- cross-run project memory
- software / hackathon / CTF / demo profiles
- task-specific evidence-backed artifact composition
- verification + completion oracle
- deterministic progress control + recovery
- persistence / resume / evaluation records
- final result persistence/presentation
- conversational TUI

## Security boundaries

```text
User request
    ↓
Task intake may narrow/select an explicitly named workspace
    ↓
WorkspaceContract is fixed
    ↓
Model output = proposal/action request
    ↓
Harness Tool Runtime / permission gate
    ↓
Evidence
    ↓
Verifier / Completion Oracle
```

The task-intake layer cannot grant a workspace that the user did not explicitly name and that does not exist locally. Multiple candidate directories are not guessed.

For ordinary local development, `execution_backend=local` is a convenience backend, not a strong sandbox. On supported Linux systems, stronger execution isolation can be requested with `linux-namespace` and strict tool isolation.

## Current limitations

- no general authenticated problem-site intake orchestrator yet;
- no persistent interactive MCP approval broker;
- MCP runtime is primarily stdio tools at present;
- no isolated untrusted plugin runtime;
- context relevance is still primarily lexical;
- project memory still needs richer decay/GC/multi-writer coordination;
- evidence-backed artifact completion verifies evidence collection + artifact existence/size, not every natural-language sentence semantically;
- local-provider endpoint self-healing is not enabled without evidence that it is needed;
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
