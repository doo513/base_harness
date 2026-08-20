---
name: configure-mcp
description: Add an explicit reviewed MCP stdio server connection to harness.toml using command argv and environment-secret references. Use after reviewing an MCP server or when connecting a known stdio MCP server.
compatibility: Verified-State Harness mcp-gateway-v1 currently supports stdio tool discovery/calls.
metadata:
  harness-action: configure-mcp
  category: connection
---
# Configure MCP

Add a reviewed MCP stdio server to Harness configuration.

Enter command arguments separately rather than a shell string. For credentials, map the environment variable required by the MCP server to an existing environment variable; only `env:NAME` references are written to TOML.

Configuration does not imply trust. Existing MCP permission and tool-isolation rules remain in force when the run starts. HTTP MCP transport is intentionally not exposed until the runtime implements it.
