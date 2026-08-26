# Base Harness V2 Agent Rules

`develop` is active. `main` is the explicit promotion target.

## Product boundary

- `runtime/packages/base-harness` is the only execution host.
- `runtime/packages/tui` is the default interactive interface.
- `src/harness/verification_v2.py` is the only verification core.
- `src/harness/verified_sidecar.py` is transport only.
- `base-harness.jsonc` is the only current configuration format.
- Do not restore the Python V1 runtime, `verified-harness`, Python TUI, or `harness.toml`.

The inherited `runtime/packages/core/src/v1` namespace is TypeScript configuration/API plumbing, not the removed Python Verified Core and not completion authority.

## Authority invariants

1. Actor, model, tool, MCP, plugin, and retrieval output is candidate data.
2. Only Core V2 may create trusted Evidence or Ready.
3. State-changing tools require an accepted root GoalContract.
4. Subagents cannot issue final Ready.
5. Verifier and protocol failures are fail-closed.
6. Repair is criterion-scoped and bounded by failure fingerprint.
7. Historical retrieval cannot self-promote.

## Working agreement

1. Read the two current documents under `docs/handoff/` before product-boundary changes.
2. Keep TypeScript host and Python sidecar protocol changes synchronized.
3. Record causal architecture changes under `docs/verification-v2/`.
4. Accept only implemented public settings.
5. Run validation only when requested by the user or controlling instructions.
6. Keep Python and runtime product versions aligned.
7. Continue on `develop` unless the user requests another branch.

Historical Stage documents are provenance only. Current source, this file, the V2 handoff, and protocol V2 are authoritative.
