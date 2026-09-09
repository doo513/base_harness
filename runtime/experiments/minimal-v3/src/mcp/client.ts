import { Client } from "@modelcontextprotocol/sdk/client/index.js"
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js"
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js"
import type { McpServerConfig } from "../config"
import type { ToolRegistry } from "../tools/registry"
import type { JsonSchema } from "../types"

export class McpConnections {
  private readonly clients: Client[] = []

  async connect(configs: Record<string, McpServerConfig>, tools: ToolRegistry): Promise<void> {
    for (const [serverName, config] of Object.entries(configs)) {
      if (config.enabled === false) continue
      const client = new Client({ name: "base-harness", version: "3.0.0" }, { capabilities: {} })
      const transport = config.command
        ? new StdioClientTransport({ command: config.command, args: config.args ?? [], env: { ...baselineEnv(), ...(config.env ?? {}) } })
        : config.url
          ? new StreamableHTTPClientTransport(new URL(config.url), { requestInit: { headers: config.headers } } as any)
          : undefined
      if (!transport) throw new Error(`MCP server ${serverName} needs command or url`)
      await client.connect(transport)
      this.clients.push(client)
      const listed = await client.listTools()
      for (const item of listed.tools) {
        if (config.include?.length && !config.include.includes(item.name)) continue
        if (config.exclude?.includes(item.name)) continue
        const localName = `mcp_${sanitize(serverName)}_${sanitize(item.name)}`
        const readOnly = item.annotations?.readOnlyHint === true
        tools.register({
          name: localName,
          toolset: `mcp:${serverName}`,
          effect: readOnly ? "read" : "external",
          risk: readOnly ? "low" : "high",
          description: item.description ?? `MCP tool ${item.name} from ${serverName}`,
          parameters: item.inputSchema as JsonSchema,
          execute: async (input) => client.callTool({ name: item.name, arguments: input }),
        })
      }
    }
  }

  async close(): Promise<void> { await Promise.allSettled(this.clients.map((client) => client.close())) }
}

const sanitize = (value: string): string => value.replace(/[^A-Za-z0-9_]/g, "_")
const baselineEnv = (): Record<string, string> => Object.fromEntries(["PATH", "Path", "PATHEXT", "SystemRoot", "HOME", "USERPROFILE", "TEMP", "TMP"].flatMap((key) => process.env[key] ? [[key, process.env[key]!]] : []))
