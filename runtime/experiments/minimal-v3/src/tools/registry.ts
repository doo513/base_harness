import type { JsonSchema } from "../types"
import type { ToolContext, ToolDefinition } from "./types"
import { ToolExecutionError } from "./types"

export class ToolRegistry {
  private readonly tools = new Map<string, ToolDefinition>()
  constructor(private readonly enabledToolsets: Set<string>) {}

  register(definition: ToolDefinition): void {
    if (this.tools.has(definition.name)) throw new Error(`Tool already registered: ${definition.name}`)
    this.tools.set(definition.name, definition)
  }

  clone(): ToolRegistry {
    const result = new ToolRegistry(new Set(this.enabledToolsets))
    for (const tool of this.tools.values()) result.register(tool)
    return result
  }

  get(name: string): ToolDefinition | undefined { return this.tools.get(name) }
  list(): ToolDefinition[] { return [...this.tools.values()].filter((tool) => this.enabledToolsets.has(tool.toolset) || tool.effect === "control") }

  schemas(predicate?: (tool: ToolDefinition) => boolean) {
    return this.list().filter((tool) => !predicate || predicate(tool)).map((tool) => {
      const parameters: JsonSchema = structuredClone(tool.parameters)
      if (tool.effect !== "read" && tool.effect !== "control") {
        parameters.properties = { ...(parameters.properties ?? {}), claimIds: { type: "array", items: { type: "string" }, description: "Accepted Claim IDs this action supports" } }
        parameters.required = [...new Set([...(parameters.required ?? []), "claimIds"])]
      }
      return { type: "function" as const, function: { name: tool.name, description: tool.description, parameters } }
    })
  }

  claimIds(name: string, input: Record<string, unknown>): string[] {
    const tool = this.tools.get(name)
    if (!tool || tool.effect === "read" || tool.effect === "control") return []
    const value = input.claimIds
    if (!Array.isArray(value) || !value.every((item) => typeof item === "string" && item.length > 0)) throw new ToolExecutionError("State-changing tools require claimIds", "CLAIM_BINDING_REQUIRED")
    return value
  }

  async execute(name: string, input: Record<string, unknown>, context: ToolContext): Promise<unknown> {
    const tool = this.tools.get(name)
    if (!tool || (!this.enabledToolsets.has(tool.toolset) && tool.effect !== "control")) throw new ToolExecutionError(`Tool is unavailable: ${name}`, "TOOL_UNAVAILABLE")
    validate(tool.parameters, input)
    const clean = { ...input }
    delete clean.claimIds
    return tool.execute(clean, context)
  }
}

function validate(schema: JsonSchema, input: Record<string, unknown>): void {
  for (const field of schema.required ?? []) if (!(field in input)) throw new ToolExecutionError(`Missing tool argument: ${field}`, "INVALID_TOOL_INPUT")
  for (const [field, value] of Object.entries(input)) {
    if (field === "claimIds") continue
    const expected = schema.properties?.[field]?.type
    if (expected === "string" && typeof value !== "string") throw new ToolExecutionError(`Tool argument ${field} must be a string`, "INVALID_TOOL_INPUT")
    if (expected === "number" && typeof value !== "number") throw new ToolExecutionError(`Tool argument ${field} must be a number`, "INVALID_TOOL_INPUT")
    if (expected === "array" && !Array.isArray(value)) throw new ToolExecutionError(`Tool argument ${field} must be an array`, "INVALID_TOOL_INPUT")
  }
}
