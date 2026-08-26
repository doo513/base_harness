# Base Harness V2 current status

Base Harness is on the V2-only product line.

```text
TUI host                    active
headless TypeScript run     active
model gateway/local LLM     TypeScript-owned
MCP/plugins/tools           TypeScript-owned
GoalContract tool gate      active
sidecar protocol            version 2 only
Evidence/Ready authority    verifier-owned
V1 Python runtime           removed
harness.toml                unsupported
```

## Verification configuration

```jsonc
{
  "verification": {
    "mode": "adaptive",
    "auto": true,
    "maxSameFailureRepairs": 2
  }
}
```

`adaptive` verifies after observed work reaches root idle. `manual` disables idle verification.

Provider, model, tool, protocol, and verifier failures retain distinct FailureKind values. Verifier failure cannot issue Ready. Repair feedback is criterion-scoped, and exhausting one fingerprint returns `blocked`.

Historical Evidence is filtered by applicability, family independence, freshness, contradiction state, and verifier revision.

There is no V1 runtime, Python TUI, `verified-harness`, `harness.toml` fallback, external OpenCode executable dependency, or V1 migration layer.

```text
develop   active V2 development
main      explicit promotion target
others    historical or frozen
```

Current source and `docs/verification-v2/` override historical Stage status documents.
