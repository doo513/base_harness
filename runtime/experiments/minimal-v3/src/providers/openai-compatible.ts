import type { ProviderConfig } from "../config"
import type { SecretRegistry } from "../security/secrets"
import type { ChatMessage, ModelDescriptor, ModelToolCall, ModelTurn } from "../types"
import type { ModelProvider, ModelRequest } from "./types"
import { ProviderError } from "./types"

const trimSlash = (value: string): string => value.replace(/\/+$/, "")

function credential(config: ProviderConfig, secrets: SecretRegistry, id: string): string | undefined {
  let value = config.apiKey
  const match = value?.match(/^\{env:([A-Za-z_][A-Za-z0-9_]*)\}$/)
  if (match) value = process.env[match[1]]
  if (!value && config.apiKeyEnv) value = process.env[config.apiKeyEnv]
  secrets.register(`${id}.api-key`, value)
  return value
}

function wireMessage(message: ChatMessage): Record<string, unknown> {
  if (message.role === "tool") return { role: "tool", content: message.content ?? "", tool_call_id: message.toolCallId }
  if (message.role === "assistant" && message.toolCalls?.length) {
    return {
      role: "assistant",
      content: message.content,
      tool_calls: message.toolCalls.map((call) => ({ id: call.id, type: "function", function: { name: call.name, arguments: call.arguments } })),
    }
  }
  return { role: message.role, content: message.content ?? "" }
}

export class OpenAICompatibleProvider implements ModelProvider {
  readonly id: string
  private readonly apiKey?: string
  private modelCache?: ModelDescriptor[]

  constructor(id: string, private readonly config: ProviderConfig, secrets: SecretRegistry) {
    this.id = id
    this.apiKey = credential(config, secrets, id)
    if (!config.baseUrl) throw new Error(`Provider ${id} requires baseUrl`)
  }

  private headers(): Record<string, string> {
    return {
      "content-type": "application/json",
      ...(this.apiKey ? { authorization: `Bearer ${this.apiKey}` } : {}),
      ...(this.config.headers ?? {}),
    }
  }

  async listModels(): Promise<ModelDescriptor[]> {
    if (this.modelCache) return this.modelCache
    const response = await fetch(`${trimSlash(this.config.baseUrl!)}/models`, { headers: this.headers() })
    if (!response.ok) throw await this.error(response, "MODEL_CATALOG_FAILED")
    const payload = await response.json() as { data?: Array<Record<string, unknown>> }
    this.modelCache = (payload.data ?? []).flatMap((item) => {
      if (typeof item.id !== "string") return []
      const reported = item.supported_reasoning_efforts ?? item.reasoning_efforts
      return [{ id: item.id, reasoningEfforts: Array.isArray(reported) ? reported.filter((value): value is string => typeof value === "string") : undefined, metadata: item }]
    })
    return this.modelCache
  }

  private async reasoningEfforts(model: string): Promise<string[] | undefined> {
    const configured = this.config.capabilities?.reasoningEfforts
    if (configured?.length) return configured
    try { return (await this.listModels()).find((item) => item.id === model)?.reasoningEfforts }
    catch { return undefined }
  }

  async complete(request: ModelRequest): Promise<ModelTurn> {
    const body: Record<string, unknown> = {
      ...(this.config.request ?? {}),
      model: request.model,
      messages: request.messages.map(wireMessage),
      tools: request.tools.length ? request.tools : undefined,
      tool_choice: request.tools.length ? "auto" : undefined,
      stream: false,
    }
    if (request.reasoningEffort) {
      const supported = await this.reasoningEfforts(request.model)
      if (!supported?.includes(request.reasoningEffort)) throw new ProviderError(`Provider did not report reasoning effort '${request.reasoningEffort}' for ${request.model}`, "REASONING_CAPABILITY_UNKNOWN")
      body.reasoning_effort = request.reasoningEffort
    }
    const response = await fetch(`${trimSlash(this.config.baseUrl!)}/chat/completions`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
    })
    if (!response.ok) throw await this.error(response, "MODEL_REQUEST_FAILED")
    const payload = await response.json() as Record<string, any>
    const choice = payload.choices?.[0]
    const raw = choice?.message
    if (!raw || raw.role !== "assistant") throw new ProviderError("Provider response did not contain an assistant message", "INVALID_PROVIDER_OUTPUT", response.status)
    const toolCalls: ModelToolCall[] | undefined = Array.isArray(raw.tool_calls)
      ? raw.tool_calls.map((item: any) => ({ id: String(item.id), name: String(item.function?.name), arguments: String(item.function?.arguments ?? "{}") }))
      : undefined
    return {
      message: { role: "assistant", content: typeof raw.content === "string" ? raw.content : null, toolCalls },
      finishReason: typeof choice.finish_reason === "string" ? choice.finish_reason : undefined,
      usage: {
        inputTokens: payload.usage?.prompt_tokens,
        outputTokens: payload.usage?.completion_tokens,
        totalTokens: payload.usage?.total_tokens,
      },
    }
  }

  private async error(response: Response, fallback: string): Promise<ProviderError> {
    let details: unknown
    try { details = await response.json() } catch { details = await response.text().catch(() => "") }
    const record = details && typeof details === "object" ? details as Record<string, any> : {}
    const code = String(record.error?.code ?? record.code ?? fallback)
    const message = String(record.error?.message ?? record.message ?? `${fallback}: HTTP ${response.status}`)
    return new ProviderError(message, code, response.status, response.status === 408 || response.status === 429 || response.status >= 500, details)
  }
}

export const registerOpenAICompatible = (registry: { register(type: string, factory: any): void }): void => {
  registry.register("openai-compatible", (id: string, config: ProviderConfig, secrets: SecretRegistry) => new OpenAICompatibleProvider(id, config, secrets))
}
