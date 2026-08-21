# Base Harness TUI UX v2 Design

Date: 2026-08-21
Status: implementation target
Scope: conversational TUI only; Kernel authority is unchanged.

## 1. Goal

Turn the current conversational launcher/monitor into a keyboard-first agent TUI with the interaction quality of common coding-agent terminals while preserving the Verified-State Harness boundary.

The UI should feel like one persistent work surface:

```text
user request
  -> transcript
  -> plan/tool/verify/recovery events
  -> fixed composer
  -> keyboard controls
```

The TUI remains a presentation/control layer. It does not create trusted facts, grant verified progress, or accept completion.

## 2. Design principles

1. **Transcript first** — show the work as a compact conversation/event stream rather than raw logs.
2. **Keyboard first** — `/` commands, Tab completion, Esc interruption, and minimal mouse dependence.
3. **Progressive disclosure** — common state stays visible; detailed runtime state remains behind `/status`, `/inspect`, or later detail views.
4. **Authority preserving** — TUI controls request runtime actions; the Kernel remains authoritative.
5. **No fake capabilities** — do not expose agents, approvals, HTTP MCP, or action-level cancellation until the underlying runtime contract exists.
6. **Cross-platform** — Windows, WSL/POSIX terminal behavior must be explicit and separately tested.

## 3. Target layout

Normal-width terminal:

```text
  /workspace/project · main
  gemini-3.5-flash · software · ready

  ❯ Add rate limiting to the login API and test it

  ◇ Plan    inspect authentication flow
  ● Read    src/api/auth.py
  ● Search  login
  ● Edit    src/api/auth.py
  ✓ Verify  18 tests passed
  ✓ Done    completion accepted

  ❯ _

  software · gemini-3.5-flash
  tab commands · / palette · esc interrupt
```

The first implementation slice stays transcript-oriented and does not create a full-screen alternate runtime. A persistent right sidebar is a Phase-2 enhancement after the interaction primitives are stable.

## 4. Header

Keep the header compact:

```text
base_harness
/workspace/project
model · profile · readiness
```

Do not show the package version in the normal TUI header. Version remains available from package/CLI metadata when needed.

Always-visible information:

- workspace
- model
- profile
- readiness

Detailed state moves to `/status`:

- context/token usage
- run id
- MCP configuration
- security flags
- memory state
- evidence counts

## 5. Composer and command palette

The input composer is the primary interaction surface.

Input modes:

```text
plain text  -> task request
/           -> command palette
@           -> workspace file picker (Phase 2)
!           -> governed shell shortcut (Phase 2)
```

The `/` palette should provide command descriptions and fuzzy/prefix completion rather than a bare command list.

Canonical visible commands:

| Command | Purpose |
| --- | --- |
| `/connect` | Connect provider or load session credential |
| `/model` | Show or switch model |
| `/sessions` | Browse resumable runs |
| `/skills` | Browse available skills |
| `/mcp` | Manage MCP configuration |
| `/status` | Show current session/runtime configuration |
| `/permissions` | Show execution boundary |
| `/workspace` | Change workspace |
| `/inspect` | Inspect a persisted run |
| `/help` | Show help |
| `/exit` | Exit the TUI |

Compatibility aliases may remain but should not dominate the palette:

```text
/models -> /model
/change -> /model
/resume -> /sessions or direct resume path
```

## 6. Transcript vocabulary

Use a small stable event vocabulary:

```text
◇ Plan     actor plan/task bookkeeping
● Tool     governed tool request/execution
✓ Verify   Harness verifier accepted evidence/claim
↻ Retry    recovery transition
↻ Adjust   strategy change
✕ Issue    meaningful failure
✓ Final    completion oracle result
✓ Done     accepted completion
■ Stop     user interruption
```

Important invariant:

```text
tool success != verified progress
verification != accepted completion
```

The visual language must keep those states separate.

## 7. Interrupt semantics

### v2.1 implemented semantic

`Esc` during an active child CLI run requests a graceful interruption of the current run.

Flow:

```text
Esc
 -> TUI sends interrupt to child process group
 -> wait for graceful exit
 -> fallback terminate/kill only after timeout
 -> persisted run files remain available for inspect/resume
```

The TUI must not report verified completion after an interrupted run.

`Ctrl+C` remains a fallback interrupt path.

### Future semantic

Action-level cancellation and run-level cancellation should eventually be distinct:

```text
Esc       -> cancel current model/tool action
Esc Esc   -> stop whole run and checkpoint
```

Do not implement this distinction by guessing in the TUI. It requires a Kernel-owned cancellation contract.

## 8. Bottom status/help line

Idle state:

```text
software · gemini-3.5-flash · ready   tab commands · / palette
```

Active run:

```text
running · workspace-name · software   esc interrupt · ctrl+c fallback
```

The line should show actions the user can actually perform. Do not advertise shortcuts that are not bound.

## 9. Sessions

`/sessions` abstracts internal run-directory paths.

Initial behavior:

```text
Sessions
  20260821-095501  completed
  20260821-093122  stopped
  20260820-221405  completed
```

Selecting/resuming through an interactive picker can follow in Phase 2. v2.1 may list recent run directories and accept `/sessions <run-id-or-path>` as a resume shortcut.

## 10. Right sidebar — Phase 2

When terminal width permits, add an optional read-only sidebar containing:

```text
Task
Context
Workspace / Git
Model
Plan progress
Permissions
MCP
Session
```

The sidebar must consume persisted/runtime-observed state only. It must never become a second authority source.

On narrow terminals the sidebar collapses automatically.

## 11. Permission UI — Phase 3

A future approval modal should look like a normal TUI interaction but be backed by a Kernel-owned approval contract.

```text
Permission required
Shell: npm install ...
Workspace: ...
Network: required

Allow once / Allow session / Deny
```

The TUI must not special-case MCP or shell execution to bypass runtime policy.

## 12. Implementation plan

### Phase 1 — this change

- remove version from normal banner
- add command descriptions to `/` completion menu
- simplify visible command vocabulary
- add `/sessions`
- improve bottom-toolbar/status wording
- add cross-platform Esc interruption while a run is active
- render explicit interrupted state
- add regression tests for palette metadata, sessions, banner, and interrupt helpers

### Phase 2

- persistent composer layout
- optional right sidebar
- `@` file picker
- interactive session picker
- diff/detail views
- richer plan progress rendering

### Phase 3

- Kernel approval contract + permission modal
- action-level cancellation contract
- provider streaming integration

## 13. Acceptance criteria for Phase 1

1. `verified-harness-tui` starts without showing the version in the normal banner.
2. Typing `/` shows commands with readable descriptions.
3. `/sessions` lists recent persisted run directories without requiring the user to know the run-root path.
4. `/sessions <run>` resumes a known run path/id through the existing CLI/runtime path.
5. While a run is active, Esc triggers the same fail-safe stop path as an explicit user interruption, with graceful interrupt before force termination.
6. Interrupted runs remain inspectable/resumable when persistence exists.
7. TUI code does not write trusted facts or synthesize completion.
8. Existing model/config/secret behavior remains unchanged.
9. Existing TUI tests remain green and new behavior has focused tests.

## 14. Non-goals

This design does not:

- replace the Verified-State Kernel;
- introduce multi-agent orchestration;
- add direct filesystem or shell authority to the UI;
- claim full-screen sidebar support in Phase 1;
- implement action-level cancellation without a runtime contract;
- weaken evidence, verification, progress, or completion gates.
