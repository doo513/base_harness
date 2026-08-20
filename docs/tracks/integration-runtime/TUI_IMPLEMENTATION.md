# base_harness TUI Implementation

Status: implemented on `main`

This document describes the terminal UI as a product/presentation layer over the existing Verified-State Harness runtime. The TUI is intentionally thin: it may collect user intent, select configuration, and render runtime state, but it does not own trusted truth, verification, recovery authority, or completion authority.

## 1. Entry point

The installed command is:

```bash
verified-harness-tui
```

`pyproject.toml` routes this command to:

```text
harness.tui_conversation:main
```

The normal user flow is therefore:

```text
Terminal
  -> tui_conversation.py
  -> shared task_intake.py
  -> RunLaunchSpec
  -> harness.cli
  -> HarnessRuntime
  -> events/tool calls/final_result.json
  -> TUI read-only presentation
```

The TUI never replaces the runtime completion oracle or verification path.

## 2. UX target

The UI borrows presentation patterns common to modern coding-agent terminals such as Claude Code, Codex CLI, OpenCode, Antigravity-style terminals, and similar tools:

- one persistent natural-language prompt
- terminal scrollback remains visible
- compact banner instead of a menu-heavy full-screen UI
- short inline plan/tool/verification/recovery events
- model/workspace/profile shown in the status area
- slash commands for explicit overrides
- final output summarized in the same conversation transcript

The implementation deliberately copies interaction patterns rather than product branding or internal architecture.

Example:

```text
╭─ base_harness 0.10.0
│  C:\work\project
│  ollama:gemma4 · software · configured
╰─ type a task · /help for commands · Ctrl+C to stop a run

❯ analyze this project and write a report
  │ Deliverable · PROJECT_ANALYSIS_REPORT.md · evidence-backed artifact contract

  Working · project · software
  Plan     inspect project structure
  ● Tool   directory.list · src
  ● Tool   file.read · pyproject.toml
  ✓ Verify architecture.entrypoint
  ↻ Retry  repair
  ✓ Final  requested artifact exists after evidence collection
  ✓ Done   accepted

  ✓ Completed
    evidence  12 observations · 3 verified facts
    output    C:\work\project\PROJECT_ANALYSIS_REPORT.md
    run       ...\runs\...
```

## 3. Main modules

### `src/harness/tui_conversation.py`

The installed conversational frontend.

Responsibilities:

- prompt loop
- natural-language task intake
- requested workspace binding
- artifact-target handoff
- model readiness check
- run launch
- live event/tool rendering
- `/resume` and `/inspect`
- read-only rendering of `final_result.json`
- `/change` conversational model-switch alias

It does not write trusted facts or synthesize completion.

### `src/harness/tui_visual.py`

Shared terminal presentation/configuration helpers.

Responsibilities:

- styles and banner
- provider connection helpers
- configured/local model discovery
- model route switching
- MCP/skill/status/permission command helpers
- local Ollama route creation
- slash completion primitives

It remains a UI/config helper layer. Task semantics come from shared task intake and runtime contracts.

### `src/harness/task_intake.py`

Shared bounded pre-runtime intake.

It may convert one explicit existing directory supplied by the user into the workspace root. It deliberately refuses to choose when multiple existing project directories are present.

For report/document requests it detects a requested artifact target. The selected domain profile is not automatically replaced with a new `research` mode.

### `src/harness/task_contracts.py`

Provides the evidence-backed artifact task overlay.

A report is accepted only after Harness-observed workspace evidence exists and the requested artifact satisfies the task completion oracle. The TUI does not replace this with a dummy shell command.

### `src/harness/final_result.py`

Persists the runtime/CLI-owned final result. The TUI only reads this record for display.

## 4. Model connection and switching

### Connect a new route

```text
/connect ollama
/connect gemini
/connect openai
/connect openai-compatible
```

API keys entered in the TUI are kept in the process/session environment. Raw secret values are not written to `harness.toml`; only environment references are persisted when required.

### Show or select models

Canonical command:

```text
/model
```

Direct selection:

```text
/model <alias>
```

Friendly alias:

```text
/change
/change <alias>
```

`/change` and `/model` have the same switching semantics. `/model` remains the canonical command because it names the resource being configured, while `/change` exists as an easier conversational alias.

Example:

```text
❯ /change
Models
  ● ollama              gemma4:latest · local
  ○ gemini              gemini-3.5-flash · api
  ○ openai              gpt-5-mini · api
Model [ollama]: gemini
  ✓ Using gemini · gemini-3.5-flash
  │ GEMINI_API_KEY is required for the next run.
API key: ********
  │ Next run model · gemini:gemini-3.5-flash
```

The change modifies `default_model` in the Harness configuration. It does not grant new tool or verification authority.

## 5. Slash commands

Current user-facing commands include:

```text
/help
/status
/connect [provider]
/model [alias]
/change [alias]      # friendly alias for /model
/models
/mcp list|search|add
/skills [query]
/mode [name]
/accept [command]
/workspace [path]
/resume <run-dir>
/inspect <run-dir>
/permissions
/new
/clear
/exit
```

Natural-language task input is the default interaction. `/skills` and `/mode` are primarily inspection/override controls rather than mandatory steps before every task.

## 6. Runtime event mapping

The TUI maps durable runtime events into short labels:

| Runtime evidence/event | TUI presentation |
| --- | --- |
| `agent.plan.replaced` | `Plan` |
| `agent.task.updated` | `Check` |
| `tool_calls.jsonl` record | `● Tool` / `✕ Tool` |
| `verification` | `✓ Verify` / `! Verify` |
| `completion.oracle` | `✓ Final` / `! Final` |
| `completion.accepted` | `✓ Done` |
| `failure` | `✕ Issue` |
| recovery events | `↻ Retry` |
| strategy events | `↻ Adjust` |

No hidden chain-of-thought is rendered. The transcript shows operational state and durable evidence-related events only.

## 7. Workspace behavior

Normal explicit-path request:

```text
❯ "C:\Users\me\Downloads\realtime_ocr" analyze and write a report
```

Pre-runtime flow:

```text
user-supplied path
  -> task_intake detects one existing directory
  -> Windows path is localized when necessary
  -> WorkspaceContract root is built for that directory
  -> actor receives tools bounded to the workspace
```

The actor does not dynamically escape the workspace during a run.

If two real directories are supplied, automatic selection is refused and the TUI keeps the existing workspace until `/workspace <path>` is used.

## 8. Evidence-backed report behavior

Report request:

```text
❯ analyze this project deeply and write a report
```

The TUI passes an artifact target to the CLI/runtime. The task overlay guides the actor through planning, inspection, evidence collection, synthesis, and recheck.

The completion oracle requires real workspace evidence such as successful `file.read`, `directory.list`, or `file.search` observations and the requested artifact. A report task is not accepted merely because a command returned exit code zero.

## 9. Local model actor protocol

The Harness actor contract requires one JSON decision per model turn:

```json
{"kind":"plan|task|tool|propose|verify_claim|retrieve|refute|complete","payload":{}}
```

### JSON normalization

`LLMController` accepts:

1. a direct JSON object
2. a JSON object inside a Markdown code fence
3. surrounding commentary when one parseable `{ ... }` object can be isolated

This is syntax repair only. A parsed decision still passes normal decision validation and runtime authority checks.

### Empty responses

Provider-level behavior:

- an empty final assistant `content` is treated as a retryable provider error
- ModelGateway may retry according to its normal route policy
- `LLMController` retains one final empty-response repair request as a last protocol guard

### Ollama thinking models

For the standard Ollama OpenAI-compatible endpoint (`:11434`), actor calls use:

```text
reasoning_effort = none
response_format = { type = json_object }
```

Reasoning text is not treated as the trusted/final actor decision. If a response contains reasoning but no final content, the provider reports an `empty_response` error instead of passing an empty string to the JSON parser.

### Task-before-plan repair

A small model may emit a `task` update before creating any plan. If the workflow contains zero tasks, the controller may normalize that first task into a one-task `plan`.

Once a plan already exists, an unknown task ID is not silently promoted into a replacement plan. The normal runtime rejection/recovery path handles the invalid task update.

## 10. Current authority boundary

```text
TUI
  can: choose config/workspace/model, start runs, render evidence
  cannot: create trusted facts or declare verified completion

Actor / LLMController
  can: plan, request tools, propose claims, request completion
  cannot: promote trusted truth

Harness Runtime / Kernel
  owns: capability policy, durable state, recovery/progress control

Verifier / Completion Oracle
  owns: claim promotion and accepted completion
```

This boundary is the primary design constraint for future TUI features.

## 11. Known limitations

- Ollama automatic discovery currently probes the local standard endpoint; WSL-to-Windows endpoint self-healing is not a general runtime resolver yet.
- Native Anthropic/Gemini provider protocols are not implemented; Gemini currently uses its OpenAI-compatible endpoint.
- TUI model switching changes future runs, not an already-running subprocess.
- MCP TUI configuration currently exposes the runtime-supported stdio path.
- The TUI is transcript-oriented rather than a full-screen Textual/OpenTUI application.
- Small local models can still violate the actor schema semantically even when JSON syntax is valid; recovery cannot guarantee that a weak model solves the task.

## 12. Verification targets

Relevant regression coverage includes:

```text
tests/test_tui_visual.py
tests/test_tui_model_change.py
tests/test_local_model_protocol_compat.py
tests/test_task_intake_artifact_contract.py
tests/test_integration_model_gateway.py
```

The release gate remains the repository's full CI plus core/stage audits; TUI tests alone are not sufficient evidence of Harness correctness.
