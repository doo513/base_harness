---
name: mcp-search
description: Search the official Model Context Protocol Registry for public MCP servers by keyword. Use when the user needs to discover MCP tools or integrations before configuring one.
compatibility: Requires network access to registry.modelcontextprotocol.io; discovery only, no automatic installation.
metadata:
  harness-action: mcp-search
  category: discovery
---
# Search MCP Registry

Search the official MCP Registry and display server name, version, description, repository, and package/remote hints when available.

This skill is intentionally read-only: finding a server never installs, executes, enables, or grants permissions to it. Review the server and then use the `configure-mcp` skill to add an explicit Harness configuration.
