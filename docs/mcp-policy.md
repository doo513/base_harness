# External Tool Policy

Codex should use local tools for local code. Search with `rg`, inspect Git with `git`, and use language tooling when the workspace provides it.

The MVP harness itself does not provide an MCP server. Project configuration must not include secrets, tokens, user-specific paths, model choices, sandbox choices, or fake local MCP commands.
