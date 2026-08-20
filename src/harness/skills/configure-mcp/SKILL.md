---
name: configure-mcp
description: Add an explicit MCP server connection to harness.toml using stdio command argv or an HTTP URL and environment-secret references. Use after reviewing an MCP server or when connecting a known MCP server.
compatibility: Verified-State Harness; current runtime primarily supports stdio tool discovery/calls.
metadata:
  harness-action: configure-mcp
  category: connection
---
# Configure MCP

Add a reviewed MCP server to Harness configuration.

For stdio, enter command arguments separately rather than a shell string. For credentials, map the environment variable required by the MCP server to an existing environment variable; only `env:NAME` references are written to TOML.

Configuration does not imply trust. Existing MCP permission and tool-isolation rules remain in force when the run starts.
