export type RuntimeFailureKind =
  | "model_provider_error"
  | "model_protocol_error"
  | "implementation_error"
  | "harness_error"

const render = (value: unknown): string => {
  try {
    return JSON.stringify(value).toLowerCase()
  } catch {
    return String(value).toLowerCase()
  }
}

export function classifyRuntimeFailure(value: unknown): RuntimeFailureKind {
  const message = render(value)
  if (
    [
      "rate limit",
      "ratelimit",
      "quota",
      "unauthorized",
      "authentication",
      "api key",
      "provider",
      "model not found",
    ].some((marker) => message.includes(marker))
  ) {
    return "model_provider_error"
  }
  if (
    [
      "invalid json",
      "protocol",
      "schema",
      "structured output",
      "response format",
    ].some((marker) => message.includes(marker))
  ) {
    return "model_protocol_error"
  }
  if (["verifier", "sidecar", "ndjson", "harness"].some((marker) => message.includes(marker))) {
    return "harness_error"
  }
  return "implementation_error"
}
