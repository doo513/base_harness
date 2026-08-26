# Base Harness V2

Base Harness V2 uses a TypeScript execution host and an independent, fail-closed Python verifier. Models may plan and act, but only Core V2 may promote Evidence or Ready.

## Product boundary

| Component | Responsibility |
| --- | --- |
| TypeScript host | TUI, sessions, model gateway, local LLM, MCP, plugins, tools, subagents |
| LLM Actor | Plans, tool requests, GoalContract proposals, evidence candidates |
| Python Core V2 | Claim validation, evidence acceptance, repair/block decisions, final Ready |

The Python V1 runtime, Python TUI/CLI, and `harness.toml` are not part of V2.

## Commands

```text
base-harness [workspace]       Start the full TUI host
base-harness run <prompt>      Run a headless task
base-harness models            List models
base-harness providers         Manage provider credentials
base-harness mcp               Manage MCP connections
```

`base-harness-verifier` is an internal sidecar. Users start `base-harness`.

## Runtime flow

```text
User
  -> TypeScript TUI or headless host
  -> GoalContract gate
  -> model, MCP, plugin, tool, and subagent execution
  -> protocol V2 candidate observations
  -> independent Python verifier
  -> ready | repair | blocked | failure
```

Protocol envelopes use `{version, id, runId, scopeId, type, payload}` with `version: 2`. Malformed NDJSON, version mismatch, verifier termination, and verifier inconsistency are fail-closed.

## Development setup

Requirements are Bun `1.3.14`, Python `3.11+`, and Git.

```powershell
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout develop
python -m pip install -e .
cd runtime
bun install --frozen-lockfile
bun run dev -- ..
```

Release ZIPs bundle both executables, so users do not need Bun, Python, OpenCode, or Gajae-Code on `PATH`.

## Configuration

V2 reads only `base-harness.jsonc`.

| Scope | Path |
| --- | --- |
| Project | `<workspace>/base-harness.jsonc` |
| Windows user | `%APPDATA%\base-harness\base-harness.jsonc` |
| Linux user | `$XDG_CONFIG_HOME/base-harness/base-harness.jsonc` or `~/.config/base-harness/base-harness.jsonc` |

There is no `harness.toml` fallback or automatic migration. Start from [`base-harness.example.jsonc`](base-harness.example.jsonc).

```jsonc
{
  "$schema": "https://base-harness.local/config.json",
  "model": "openai/your-model",
  "verification": {
    "mode": "adaptive",
    "auto": true,
    "maxSameFailureRepairs": 2
  },
  "provider": {
    "openai": {
      "options": { "apiKey": "{env:OPENAI_API_KEY}" }
    }
  },
  "mcp": {}
}
```

| Verification setting | Implemented behavior |
| --- | --- |
| `mode: "adaptive"` | Verify after a tool-producing root session becomes idle |
| `mode: "manual"` | Disable idle verification and use `/verify` |
| `auto` | Enable or disable adaptive idle verification |
| `maxSameFailureRepairs` | Limit repair attempts for one failure fingerprint |

Unsupported verification settings are rejected by the schema rather than silently ignored.

## TUI controls

```text
/goal       Show the root GoalContract
/verify     Request independent verification
/evidence   Show evidence and candidate counts
/harness    Toggle the verification panel or overlay
```

Wide terminals use the sidebar panel and narrow terminals use the overlay. Subagents have separate scopes; only the root GoalContract can receive final Ready.

## Storage

| Data | Windows | Linux |
| --- | --- | --- |
| Runtime state and verifier artifacts | `%LOCALAPPDATA%\base-harness` | `$XDG_STATE_HOME/base-harness` or `~/.local/state/base-harness` |
| User configuration | `%APPDATA%\base-harness` | `$XDG_CONFIG_HOME/base-harness` or `~/.config/base-harness` |

Credentials remain in the TypeScript host. The verifier receives redacted metadata, artifact paths, and hashes.

## Build and release

```powershell
cd runtime
bun run build:release windows-x64
cd ..
python runtime/script/package-release.py --target windows-x64 --repo .
```

Use `linux-x64` and `python3` for Linux.

## Current documentation

- [Verification V2 implementation and meta audit](docs/verification-v2/IMPLEMENTATION_AND_META_AUDIT.md)
- [V2-only migration](docs/verification-v2/V2_ONLY_MIGRATION.md)

Historical audit, track, and evidence files are provenance only and do not define the current runtime.
