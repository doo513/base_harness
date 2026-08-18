# Phase 02 — Config and Secret Resolution

Status: IMPLEMENTED; targeted tests added; full regression remains enforced by `develop` CI.

## Problem / evidence

The runtime CLI previously required almost all integration settings as individual flags and model credentials had no common contract. Model/MCP/plugin work would otherwise invent separate configuration paths and risk persisting raw secrets.

## Contract

- standard-library TOML loader with a typed `HarnessConfig`;
- one configuration vocabulary for workspace, model providers, MCP servers, plugins, and security defaults;
- credentials are references, currently `env:NAME`, not inline secret values;
- secret resolution is explicit and fails closed when the referenced environment value is missing;
- descriptors record the secret reference but never the resolved value;
- CLI flags may override execution choices while the config supplies defaults;
- provider/MCP/plugin execution itself remains owned by later phases.

## Implementation

- added `harness.config` with `HarnessConfig`, `ModelConfig`, `MCPServerConfig`, `PluginConfig`, `WorkspaceConfig`, `SecretRef`, and `SecretResolver`;
- added strict top-level config-key validation and duplicate extension-name checks;
- added `--config` to the CLI;
- CLI now constructs `WorkspaceContract` from config workspace settings and uses config profile/run/security defaults;
- CLI version text now reads `harness.__version__` instead of a stale hard-coded version;
- added `harness.example.toml` using environment references only;
- added `tests/test_integration_config.py`.

## Structural review

- config data does not directly mutate `HarnessState`;
- resolved secrets are not included in `HarnessConfig.descriptor()`;
- Model/MCP/plugin sections are declarative only at this phase and therefore cannot bypass Kernel tool/capability/verification gates;
- Workspace config is converted to the Phase 01 contract before runtime creation.

## Validation focus

Targeted tests cover typed parsing, missing-secret fail-closed behavior, rejection of inline secret syntax, unknown top-level fields, undeclared default models, and duplicate MCP/plugin names.

## Remaining limitations

- only environment-variable secret references are implemented; OS keyring/secret manager support can be added behind the same `SecretResolver` boundary if needed;
- model sections are consumed by Phase 03 Model Gateway;
- MCP/plugin sections are consumed by Phase 06;
- config migration/versioning beyond schema `harness-config-v1` is deferred until a second schema exists.
