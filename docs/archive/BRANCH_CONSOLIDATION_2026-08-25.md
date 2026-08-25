# Branch Consolidation Record — 2026-08-25

## Purpose

The repository branch model is intentionally reduced to three long-lived branches:

- `main`: stable, reviewed integration baseline.
- `develop`: active development and integration branch.
- `pre-main`: historical fallback / backup snapshot.

All other temporary, experiment, review, or work branches listed below were reviewed before removal. This document preserves the branch purpose, branch-tip identity, and any design information that remains useful after consolidation.

## Removed branch inventory

| Branch | Tip before cleanup | Relationship to retained history | Preservation decision |
|---|---|---|---|
| `environment-foundation-review` | `b9da9374e156b5cb8ab24813791092cb7514bd85` | ancestor of current `main`; no commits ahead of `main` | branch pointer only; no separate code snapshot required |
| `environment-foundation-v1` | `b9da9374e156b5cb8ab24813791092cb7514bd85` | same tip as `environment-foundation-review`; no commits ahead of `main` | duplicate branch pointer; no separate snapshot required |
| `p1-memory-v2` | `b9da9374e156b5cb8ab24813791092cb7514bd85` | same tip as both environment branches; no commits ahead of `main` | duplicate historical pointer; no separate snapshot required |
| `__noop_should_not_create` | `0b075cdedf7367280810d00267ee3de901fd637b` | ancestor of current `main`; no unique commits | test/no-op branch; no content preservation required |
| `work/p0-foundation` | `143f71554b2c93c60bd1491739797dbc09915edd` | diverged historical work branch; 14 commits ahead of its merge base | preserve its design intent and map the useful work to current `develop` |

## `work/p0-foundation` preservation record

The work branch concentrated on the P0 execution/configuration foundation. Its relevant historical concerns were:

1. **TUI/CLI shared configuration**
   - Start TUI from the invocation directory, with home fallback.
   - Keep explicit workspace override semantics.
   - Persist TUI changes to shared TOML so CLI and TUI do not maintain independent state.
   - Keep `/domain` as the canonical TUI domain selector while preserving compatibility aliases.

2. **Execution-backend / completion-oracle boundary**
   - Completion commands must not silently create a fresh host-local execution path when Actor tools use another backend.
   - Command completion oracles receive an explicit backend and can fail closed when strong filesystem isolation is required.
   - Linux namespace acceptance execution uses an isolated namespace backend rather than reopening the host boundary.
   - Local execution remains explicitly unisolated rather than being represented as a strong isolation boundary.

3. **TUI configuration surface**
   - The branch introduced/changed TUI config, visual, conversation, and CLI integration paths.
   - It added regression tests around TUI config and completion-oracle behavior.

4. **Remaining foundation work recorded at the time**
   - task/capability/environment preflight composition;
   - structured workspace write/diff/checkpoint and rollback;
   - durable user-question/approval/pause/cancel control;
   - runtime skill selection with enforced tool subsets.

### Current `develop` mapping

The central P0 design document already exists in `develop` as:

- `docs/tracks/integration-runtime/P0_TUI_CONFIG_ORACLE_BOUNDARY.md`

Its decision content matches the branch version reviewed before consolidation. Current `develop` also contains newer or superseding work in the same areas, including TUI/model integration, model boundary hardening, execution/oracle configuration, MCP/plugin boundary work, and associated regression tests.

Historical files associated with this branch included changes around:

- `src/harness/cli.py`
- `src/harness/config.py`
- `src/harness/core/oracles.py`
- `src/harness/tui.py`
- `src/harness/tui_config.py`
- `src/harness/tui_conversation.py`
- `src/harness/tui_visual.py`
- `src/harness/profiles/software.py`
- `src/harness/profiles/hackathon.py`
- `src/harness/skill_actions.py`
- `tests/test_p0_tui_config_oracle.py`

The branch is therefore retained as **documented historical design provenance**, not as a long-lived source branch.

## Consolidation rule going forward

New experiments should normally branch from `develop` and be merged or discarded promptly. Long-lived branch responsibilities are fixed as:

```text
pre-main   historical fallback / backup
    \
main       stable reviewed baseline
    \
develop    active development and integration
```

Temporary branches must not become additional architecture authorities. If a temporary branch contains a design decision that should survive branch deletion, that decision should first be promoted into `docs/` on `develop` with the relevant commit/branch provenance recorded.
