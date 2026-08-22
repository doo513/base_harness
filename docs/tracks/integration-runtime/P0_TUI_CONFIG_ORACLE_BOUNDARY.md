# P0 — TUI/CLI Configuration and Completion-Oracle Boundary

Status: implementation and regression target.

## Decisions

1. The TUI starts in the directory from which the user invoked it. If that directory is unavailable, it falls back to the user home directory.
2. `--workspace` and `/workspace <path>` remain explicit overrides. `/workspace` without an argument prompts with the current workspace.
3. The default shared config is a local `harness.toml` when one already exists; otherwise it is stored under the user's config directory below the home profile.
4. TUI changes to domain, workspace, fixed acceptance command, model/MCP configuration, and permission preset are persisted to TOML. The CLI reads the same TOML.
5. `/domain` is the canonical TUI command. `/mode` remains a compatibility alias. The CLI retains `--profile` as the stable automation interface for Codex and other agents.
6. A TUI launch no longer emits `--no-strict-*`, `--execution-backend local`, or `--network-policy allow` unless explicitly requested. Persisted TOML policy remains authoritative.
7. `CommandCompletionOracle` no longer creates a fresh host-local backend. It receives an explicit independent oracle backend, records its attestation, and can fail closed when filesystem isolation is required.
8. On Linux namespace runs, ordinary acceptance tests use a separate network-denied namespace backend. Sealed acceptance keeps its read-only sealed-asset mount contract. Local mode remains explicitly unisolated rather than being mislabeled as safe.

## Remaining P0 work

- task/capability/environment preflight composition;
- structured workspace write/diff/checkpoint tools and filesystem rollback;
- durable user-question/approval/pause/action-cancel control channel;
- runtime Skill selection with enforced tool subsets.
