# Base Harness V2 current handoff

```text
product version    2.0.0
execution host     TypeScript base-harness runtime
interactive host   @base-harness/tui
verification core Python protocol V2 sidecar
configuration      base-harness.jsonc
active branch      develop
```

The Python V1 CLI/runtime, profiles, probes, and TOML configuration are removed. Git history retains them.

## Mandatory boundaries

- Actor output is never trusted evidence by itself.
- State-changing tools require an accepted GoalContract.
- The verifier owns Evidence and Ready.
- Root scope alone can receive final Ready.
- Protocol failures are fail-closed.
- V1 runtime and `harness.toml` fallbacks must not be restored.

## Current entry points

| Concern | Path |
| --- | --- |
| Product CLI and TUI | `runtime/packages/base-harness` |
| TUI components | `runtime/packages/tui` |
| NDJSON client | `runtime/packages/verification` |
| Verifier | `src/harness/verification_v2.py` |
| Sidecar transport | `src/harness/verified_sidecar.py` |
| Configuration example | `base-harness.example.jsonc` |

Read `docs/handoff/02_CURRENT_STATUS.md` and `README.md` for the current product.
