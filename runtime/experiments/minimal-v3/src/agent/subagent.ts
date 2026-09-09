import { runReadOnlySubagent } from "./loop"
import type { ModelProvider } from "../providers/types"
import type { ToolRegistry } from "../tools/registry"

export function registerSubagentTool(input: { registry: ToolRegistry; provider: ModelProvider; model: string; reasoningEffort?: string; workspace: string }): void {
  input.registry.register({
    name: "delegate_readonly",
    toolset: "subagent",
    effect: "read",
    risk: "low",
    description: "Delegate bounded read-only workspace exploration to a child agent.",
    parameters: { type: "object", properties: { task: { type: "string" } }, required: ["task"], additionalProperties: false },
    execute: async (args) => ({ report: await runReadOnlySubagent({ provider: input.provider, model: input.model, reasoningEffort: input.reasoningEffort, tools: input.registry, workspace: input.workspace, prompt: String(args.task) }) }),
  })
}
