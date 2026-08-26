# Base Harness V2-only migration

## Cause

The repository exposed the original Python runtime and the new TypeScript runtime at the same time. This made the default host, configuration source, completion authority, and supported commands ambiguous.

## Decision

Base Harness 2.0 uses the TypeScript runtime and full TUI as its only execution host. Python is packaged only as the fail-closed protocol V2 verifier sidecar.

## Removed

- Python `verified-harness` CLI and runtime kernel.
- Python profiles, gateways, plugins, skills, recovery loop, tests, and probes.
- `harness.toml` and its example.
- V1-specific Python CI workflows.

## Current surface

- `base-harness [workspace]` starts the full TUI.
- `base-harness run <prompt>` is the headless path.
- `base-harness.jsonc` is the only configuration format.
- Protocol version 2 is the only verification protocol.
- Only the verifier may issue Evidence or Ready.

Public verification settings are `mode`, `auto`, and `maxSameFailureRepairs`. Unsupported checks and the unused `always` mode were removed.

There is no V1 fallback or migration layer. Historical documents remain provenance only.
