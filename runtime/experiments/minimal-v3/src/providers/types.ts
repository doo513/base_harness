import type { ChatMessage, JsonSchema, ModelDescriptor, ModelTurn } from "../types"

export interface ModelRequest {
  model: string
  messages: ChatMessage[]
  tools: Array<{ type: "function"; function: { name: string; description: string; parameters: JsonSchema } }>
  reasoningEffort?: string
}

export interface ModelProvider {
  readonly id: string
  complete(request: ModelRequest): Promise<ModelTurn>
  listModels(): Promise<ModelDescriptor[]>
}

export class ProviderError extends Error {
  constructor(
    message: string,
    readonly code: string,
    readonly status?: number,
    readonly retryable = false,
    readonly details?: unknown,
  ) { super(message); this.name = "ProviderError" }
}
