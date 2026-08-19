# Phase 06 — MCP / Plugin Gateway

Status: IMPLEMENTED; targeted protocol/security tests added; HTTP MCP and isolated plugin hosting remain deferred.

## Problem / evidence

The pre-integration runtime had a strong `ActionRuntime` but no external tool discovery/registration path. Directly executing provider/MCP/plugin actions would bypass the existing capability, permission, observation, verification, and resume boundaries.

External protocol evidence reviewed for this phase:

- official Model Context Protocol 2026-07-28 architecture/lifecycle material: the modern protocol removes the legacy initialize handshake and carries protocol/client metadata per request;
- official compatibility guidance: stdio clients may probe modern discovery and fall back to the 2025 initialize/initialized era;
- official tools contract: tools expose input/output JSON Schemas and annotations are hints, not trustworthy authorization data;
- current MCP tool schemas may use full JSON Schema 2020-12, which is broader than the harness Phase-05 local validator.

## Contract

- MCP/plugin tools are normalized into the existing `ActionRuntime`; they never execute around it;
- MCP server annotations never select capability, side-effect, permission, or idempotence policy;
- absent operator policy, discovered MCP tools default to `EXTERNAL + confirm + non-idempotent`;
- modern stdio discovery is attempted first, with bounded legacy initialize fallback;
- provider MCP schemas are preserved for model call generation but are not falsely claimed to be fully enforced by the local schema subset;
- MCP/plugin tool schema hashes are included in tool provenance so resume configuration changes fail closed;
- Python plugins are explicit, already-installed trusted extensions only: no auto-install and no auto-discovery;
- because plugin import and the v1 MCP stdio client execute in the host process, `strict_tool_isolation` rejects enabled MCP/plugins rather than pretending they are isolated.

## Implementation

### MCP

- added `MCPStdioClient` with line-delimited JSON-RPC, bounded request/probe timeouts, sanitized process environment, and argv execution (`shell=False`);
- added modern `server/discover` path for protocol `2026-07-28` and legacy `initialize` fallback;
- added bounded/paginated `tools/list` discovery and `tools/call` execution;
- normalized names as `mcp.<server>.<tool>`;
- preserved MCP input/output schemas on model-visible tool contracts;
- added explicit per-tool config policy via `options.tool_policies`;
- MCP secrets resolve only from configured secret references.

### Plugins

- added `PluginManifest` / `PluginGateway` with API version `harness-plugin-v1`;
- explicitly enabled module must expose `harness_plugin(options=...)`;
- config/manifest identity mismatch fails closed;
- contributed tools are namespaced as `plugin.<plugin>.<tool>` and retain the existing ActionRuntime security path;
- no package installation, filesystem scan, or implicit entry-point discovery is performed.

### Composition

- added profile tool augmentation that preserves the concrete domain profile instance/type;
- rejects tool-name collisions;
- stamps local/provider schema hashes into tool provenance for resume drift detection;
- CLI automatically adds bounded workspace READ tools to non-demo profiles and configured MCP/plugin tools when enabled.

## Structural/security review

- external tool execution still passes through capability checks, permission checks, durable receipts/observations, and normal verification;
- MCP `isError` is mapped to failed tool postcondition rather than a successful observation;
- MCP annotations are recorded as `untrusted_hint` only;
- default MCP policy cannot auto-execute in the current non-interactive CLI because `confirm` has no approval source; explicit operator policy or the later TUI approval path is required;
- strict tool isolation rejects MCP/plugin v1 before runtime construction;
- full MCP schemas are model-visible but marked provider-validated; the local JSON-Schema subset is not presented as full MCP validation;
- domain profile class/source identity remains stable after tool augmentation, while tool/schema changes remain fingerprinted through existing manifest tool descriptors.

## Validation focus

`tests/test_integration_mcp_plugin.py` covers:

- modern stdio discovery and tool call;
- legacy handshake fallback;
- MCP schema preservation;
- operator policy versus untrusted server annotations;
- conservative default permission/side-effect policy;
- explicit enabled-plugin loading and disabled-plugin non-loading;
- plugin manifest/config identity rejection;
- profile identity preservation, collision rejection, and schema provenance hashing;
- malformed MCP/plugin config rejection.

## Remaining limitations

- HTTP MCP transport is represented in config but not implemented by `mcp-gateway-v1`;
- server-initiated sampling/elicitation/roots, prompts, resources, subscriptions, tasks, and logging are outside this minimal tool-use phase;
- Python plugin import is a trusted host-code extension boundary, not a sandbox;
- isolated MCP/plugin hosting may be added later behind a dedicated execution backend if real workloads justify it;
- successful live interoperability against third-party MCP servers remains part of Real E2E evidence.
