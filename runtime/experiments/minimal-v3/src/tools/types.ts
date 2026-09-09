import type { JsonSchema, Risk, ToolEffect } from "../types"

export interface ToolContext { workspace: string; signal?: AbortSignal }
export interface ToolDefinition {
  name: string
  description: string
  toolset: string
  effect: ToolEffect
  risk: Risk
  parameters: JsonSchema
  execute(input: Record<string, unknown>, context: ToolContext): Promise<unknown>
}

export class ToolExecutionError extends Error {
  constructor(message: string, readonly code: string, readonly details?: unknown) { super(message); this.name = "ToolExecutionError" }
}
