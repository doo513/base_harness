# 01. V2 Runtime and Interface

## Situation

The V1 Python shell/TUI and the independent TypeScript runtime exposed overlapping execution paths, while missing `run/` modules, theme assets, and generated SDK contracts prevented a reproducible local launch.

## Reason

A single executable Host is required so model selection, provider authentication, local models, MCP, tools, sessions, subagents, TUI, and verification use one runtime contract.

## Action

- Kept the independent OpenCode-derived TypeScript runtime as the execution Host.
- Kept the Python V2 verifier as an independent sidecar instead of a second execution runtime.
- Restored and unignored the CLI `run/` module tree.
- Added the Base Harness theme asset and model catalog fallback.
- Standardized `base-harness.jsonc`, verification fields, public flags, and generated SDK types.
- Added Host API surfaces for harness status, verification, and cancellation.

## Result

`base-harness [workspace]` and `base-harness run <prompt>` now enter the same Host runtime, and TUI/headless consumers use generated Host contracts instead of directly owning verifier policy.

## Evidence

- `base-harness --help` exited with code 0.
- Core, Host, SDK, TUI, schema, and verification type checks passed during implementation.
- The CLI `run/` files are no longer hidden by the root `run/` ignore rule.
- The Base Harness theme regression suite passed 8 tests.
