import { createHash, randomUUID } from "node:crypto"

export type FailureKind =
  | "model_provider_error"
  | "model_protocol_error"
  | "tool_execution_error"
  | "implementation_error"
  | "workspace_conflict"
  | "verifier_error"
  | "harness_error"
  | "unknown_failure"

export type RuntimeFailureKind = FailureKind
export type FailureSource = "model" | "provider" | "tool" | "workspace" | "verifier" | "harness"
export type FailureProducer = "model_gateway" | "tool_host" | "orchestrator" | "verifier_sidecar"

export interface FailureEnvelope {
  version: 1
  id: string
  runId: string
  scopeId: string
  actionId?: string
  kind: FailureKind
  source: FailureSource
  producer: FailureProducer
  phase: string
  code?: string
  status?: number
  tag?: string
  retryable: boolean
  terminal: boolean
  classificationSource: "typed" | "status" | "provider_code" | "heuristic"
  confidence: "high" | "medium" | "low"
  message: string
  details?: unknown
}

type RecordValue = Record<string, unknown>
const record = (value: unknown): RecordValue | undefined =>
  typeof value === "object" && value !== null && !Array.isArray(value) ? (value as RecordValue) : undefined
const asString = (value: unknown) => (typeof value === "string" ? value : undefined)
const asNumber = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : undefined)

const render = (value: unknown): string => {
  if (value instanceof Error) return value.message
  const item = record(value)
  if (typeof item?.message === "string") return item.message
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

const providerTags = new Set([
  "InvalidRequest",
  "NoRoute",
  "Authentication",
  "RateLimit",
  "QuotaExceeded",
  "ContentPolicy",
  "ProviderInternal",
  "Transport",
  "UnknownProvider",
])
const protocolCodes = new Set([
  "invalid_provider_output",
  "invalid_response_format",
  "response_schema_error",
  "schema_validation_error",
])
const providerCodes = new Set([
  "authentication_error",
  "invalid_api_key",
  "invalid_request_error",
  "model_not_found",
  "quota_exceeded",
  "rate_limit_exceeded",
  "resource_exhausted",
  "provider_internal_error",
  "service_unavailable",
  "transport_error",
])
const transientProviderCodes = new Set([
  "rate_limit_exceeded",
  "resource_exhausted",
  "provider_internal_error",
  "service_unavailable",
  "transport_error",
])

const typed = (value: unknown) => {
  const top = record(value)
  const data = record(top?.data)
  const reason = record(top?.reason) ?? record(data?.reason) ?? record(top?.cause)
  const tag = asString(reason?._tag) ?? asString(top?._tag) ?? asString(top?.name)
  const code = asString(reason?.code) ?? asString(top?.code) ?? asString(data?.code) ?? tag
  const response = record(record(reason?.http)?.response)
  const status = asNumber(response?.status) ?? asNumber(reason?.status) ?? asNumber(top?.statusCode) ?? asNumber(data?.statusCode)
  const retryable = typeof top?.retryable === "boolean" ? top.retryable : undefined
  return { tag, code, status, retryable }
}

export function createFailureEnvelope(input: {
  runId: string
  scopeId: string
  actionId?: string
  source: FailureSource
  producer: FailureProducer
  phase: string
  error: unknown
}): FailureEnvelope {
  const info = typed(input.error)
  const message = render(input.error)
  const lower = message.toLowerCase()
  let kind: FailureKind = "unknown_failure"
  let classificationSource: FailureEnvelope["classificationSource"] = "heuristic"
  let confidence: FailureEnvelope["confidence"] = "low"
  let retryable = info.retryable ?? false

  if (input.source === "tool" && input.producer === "tool_host") {
    kind = "tool_execution_error"
    classificationSource = "typed"
    confidence = "high"
  } else if (input.source === "workspace") {
    kind = "workspace_conflict"
    classificationSource = "typed"
    confidence = "high"
  } else if (input.source === "verifier") {
    kind = "verifier_error"
    classificationSource = "typed"
    confidence = "high"
  } else if (input.source === "harness") {
    kind = "harness_error"
    classificationSource = "typed"
    confidence = "high"
  } else if (info.tag === "InvalidProviderOutput") {
    kind = "model_protocol_error"
    classificationSource = "typed"
    confidence = "high"
  } else if (info.tag && (providerTags.has(info.tag) || providerTags.has(info.tag.replace(/Error$/, "")))) {
    kind = "model_provider_error"
    classificationSource = "typed"
    confidence = "high"
  } else if (info.code && protocolCodes.has(info.code.toLowerCase())) {
    kind = "model_protocol_error"
    classificationSource = "provider_code"
    confidence = "high"
    retryable = false
  } else if (info.code && providerCodes.has(info.code.toLowerCase())) {
    kind = "model_provider_error"
    classificationSource = "provider_code"
    confidence = "high"
    retryable = transientProviderCodes.has(info.code.toLowerCase())
  } else if (info.status !== undefined) {
    kind = input.source === "model" || input.source === "provider" ? "model_provider_error" : "unknown_failure"
    classificationSource = "status"
    confidence = "medium"
    retryable = info.status === 429 || info.status >= 500
  } else if (["invalid json", "structured output", "response format", "schema mismatch"].some((x) => lower.includes(x))) {
    kind = "model_protocol_error"
  } else if (["rate limit", "ratelimit", "quota", "unauthorized", "authentication", "model not found"].some((x) => lower.includes(x))) {
    kind = "model_provider_error"
    retryable = /rate.?limit|temporar|overload/.test(lower)
  }

  return {
    version: 1,
    id: randomUUID(),
    runId: input.runId,
    scopeId: input.scopeId,
    actionId: input.actionId,
    kind,
    source: input.source,
    producer: input.producer,
    phase: input.phase,
    code: info.code,
    status: info.status,
    tag: info.tag,
    retryable,
    terminal: kind === "harness_error" || kind === "verifier_error",
    classificationSource,
    confidence,
    message,
    details: input.error,
  }
}

export function failureFingerprint(envelope: FailureEnvelope, criterion = "", repairTarget = "") {
  return createHash("sha256")
    .update(
      JSON.stringify({
        kind: envelope.kind,
        code: envelope.code ?? "",
        source: envelope.source,
        phase: envelope.phase,
        scopeId: envelope.scopeId,
        criterion,
        repairTarget,
      }),
    )
    .digest("hex")
}

export function isFailureEnvelope(value: unknown): value is FailureEnvelope {
  const item = record(value)
  return (
    item?.version === 1 &&
    typeof item.id === "string" &&
    typeof item.runId === "string" &&
    typeof item.scopeId === "string" &&
    typeof item.kind === "string" &&
    typeof item.source === "string" &&
    typeof item.producer === "string" &&
    typeof item.phase === "string"
  )
}

export const classifyRuntimeFailure = (value: unknown): FailureKind =>
  createFailureEnvelope({
    runId: "unscoped",
    scopeId: "unscoped",
    source: "model",
    producer: "model_gateway",
    phase: "response",
    error: value,
  }).kind
