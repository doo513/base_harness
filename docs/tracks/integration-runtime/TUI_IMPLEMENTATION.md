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
    run       <user-local-state>\base_harness\runs\...
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
- isolated secret input session for API keys

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

Secret input uses a dedicated short-lived `PromptSession` in password mode. The long-lived conversation `PromptSession` is never switched into password mode, so later `❯` prompts remain visible and the API key does not share the normal conversation input session/history.

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

❯ this input is visible normally
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

## 7. Workspace and run-state behavior

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

TUI-created run state is kept outside the project by default:

```text
Windows
  %LOCALAPPDATA%\base_harness\runs\<run-id>

POSIX
  $XDG_STATE_HOME/base_harness/runs/<run-id>
  or ~/.local/state/base_harness/runs/<run-id>
```

`HARNESS_RUN_ROOT` may explicitly override this default. Separating run/evidence state from the actor workspace is a safer default topology and is compatible with later strict-layout enforcement.

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

## 11. Windows TUI / artifact incident and remediation

A Windows run on 2026-08-20 exposed three distinct issues. They are recorded in detail in `WINDOWS_TUI_ARTIFACT_INCIDENT_2026-08-20.md`.

### A. Conversation input stayed masked after API-key entry

**Cause:** the same long-lived `PromptSession` was used for ordinary conversation and a prompt call with `is_password=True`.

**Result:** later normal prompts rendered as `********` even though their values were ordinary task text.

**Fix:** API-key input now uses a dedicated short-lived password `PromptSession`; the normal conversation session is never mutated into secret mode.

### B. Successful Windows tool evidence failed during progress verification

Observed sequence:

```text
Plan
-> directory.list succeeds
-> observation artifact is persisted
-> progress controller verifies the content-addressed observation
-> artifact directory open fails on Windows with Errno 13
-> fail-closed checkpoint_stop
```

**Cause:** the verified-read path used POSIX descriptor-relative directory opening (`dir_fd`, `O_DIRECTORY`, `O_NOFOLLOW`-style semantics). That hardening path is not portable to Windows.

**Result:** tool execution itself had succeeded, but deterministic Stage-06 progress evidence verification could not re-open the artifact and correctly stopped the run.

**Fix:** POSIX keeps the descriptor-relative path. Windows uses a separate portable verified-read path that confines the opaque artifact basename to the artifact root, rejects symlink/non-regular artifacts, reads the resolved regular file, and verifies the exact returned bytes against the SHA-256 digest encoded in the artifact reference.

This preserves content-integrity validation. The Windows fallback cannot provide the exact same descriptor-relative no-follow primitive as the POSIX path, so the platform distinction is explicit rather than hidden.

### C. Kernel run state was created inside the actor workspace

**Cause:** TUI defaults historically used `./runs/<timestamp>`.

**Result:** actor workspace and kernel/evidence state could overlap whenever the TUI was launched from the project directory. This was not the cause of the Windows `PermissionError`, but it weakened the intended topology.

**Fix:** default TUI run state now uses the user-local Harness state directory described in section 7.

## 12. Known limitations

- Ollama automatic discovery currently probes the local standard endpoint; WSL-to-Windows endpoint self-healing is not a general runtime resolver yet.
- Native Anthropic/Gemini provider protocols are not implemented; Gemini currently uses its OpenAI-compatible endpoint.
- TUI model switching changes future runs, not an already-running subprocess.
- MCP TUI configuration currently exposes the runtime-supported stdio path.
- The TUI is transcript-oriented rather than a full-screen Textual/OpenTUI application.
- Small local models can still violate the actor schema semantically even when JSON syntax is valid; recovery cannot guarantee that a weak model solves the task.
- Windows artifact verification retains content-address/root-confinement/regular-file checks, but the exact POSIX descriptor-relative no-follow primitive is platform-specific and therefore not claimed on Windows.

## 13. Verification targets

Relevant regression coverage includes:

```text
tests/test_tui_visual.py
tests/test_tui_model_change.py
tests/test_local_model_protocol_compat.py
tests/test_task_intake_artifact_contract.py
tests/test_integration_model_gateway.py
tests/test_windows_tui_artifact_compat.py
```

`test_windows_tui_artifact_compat.py` specifically covers the portable artifact verified-read path, tamper rejection, external default run-state root, and isolated secret prompt session.

The release gate remains the repository's full CI plus core/stage audits; TUI tests alone are not sufficient evidence of Harness correctness.
