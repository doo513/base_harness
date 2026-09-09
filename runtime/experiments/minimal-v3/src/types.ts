export type Risk = "low" | "medium" | "high" | "critical"
export type ToolEffect = "read" | "workspace_write" | "external" | "control"

export interface JsonSchema {
  type?: string
  description?: string
  properties?: Record<string, JsonSchema>
  required?: string[]
  items?: JsonSchema
  enum?: unknown[]
  additionalProperties?: boolean | JsonSchema
  [key: string]: unknown
}

export interface ModelToolCall {
  id: string
  name: string
  arguments: string
}

export interface ChatMessage {
  role: "system" | "user" | "assistant" | "tool"
  content: string | null
  toolCallId?: string
  toolCalls?: ModelToolCall[]
}

export interface ModelTurn {
  message: ChatMessage
  finishReason?: string
  usage?: { inputTokens?: number; outputTokens?: number; totalTokens?: number }
}

export interface ModelDescriptor {
  id: string
  reasoningEfforts?: string[]
  metadata?: Record<string, unknown>
}
