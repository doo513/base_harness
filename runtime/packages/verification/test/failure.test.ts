import { expect, test } from "bun:test"
import { createFailureEnvelope, failureFingerprint, isTrustedFailureEnvelope } from "../src/failure"

const input = {
  runId: "run-1",
  scopeId: "scope-1",
  source: "provider" as const,
  producer: "model_gateway" as const,
  phase: "model.generate",
}

test("only the host-created envelope carries the non-serializable trust brand", () => {
  const envelope = createFailureEnvelope({
    ...input,
    error: { reason: { _tag: "RateLimitError", status: 429 }, message: "limited" },
  })

  expect(isTrustedFailureEnvelope(envelope)).toBe(true)
  expect(isTrustedFailureEnvelope({ ...envelope })).toBe(false)
  expect(JSON.stringify(envelope)).not.toContain("trusted-failure")
})

test("typed provider tag classifies Korean messages independently of wording", () => {
  const first = createFailureEnvelope({
    ...input,
    error: { message: "요청 한도를 초과했습니다", reason: { _tag: "RateLimitError", status: 429 } },
  })
  const second = createFailureEnvelope({
    ...input,
    error: { message: "잠시 후 다시 시도하세요", reason: { _tag: "RateLimitError", status: 429 } },
  })

  expect(first.kind).toBe("model_provider_error")
  expect(first.classificationSource).toBe("typed")
  expect(first.confidence).toBe("high")
  expect(failureFingerprint(first, "criterion-1", "scope-1")).toBe(
    failureFingerprint(second, "criterion-1", "scope-1"),
  )
})

test("InvalidProviderOutput is a model protocol failure", () => {
  const result = createFailureEnvelope({
    ...input,
    source: "model",
    error: { message: "응답 스키마가 맞지 않습니다", reason: { _tag: "InvalidProviderOutput" } },
  })

  expect(result.kind).toBe("model_protocol_error")
  expect(result.classificationSource).toBe("typed")
  expect(result.retryable).toBe(false)
})

test("provider codes take precedence over HTTP status and message heuristics", () => {
  const result = createFailureEnvelope({
    ...input,
    error: {
      message: "한국어 제공자 오류",
      code: "rate_limit_exceeded",
      status: 503,
    },
  })

  expect(result.kind).toBe("model_provider_error")
  expect(result.classificationSource).toBe("provider_code")
  expect(result.confidence).toBe("high")
  expect(result.retryable).toBe(true)
})

test("tool-host provenance cannot be reclassified as a model provider failure", () => {
  const result = createFailureEnvelope({
    ...input,
    source: "tool",
    producer: "tool_host",
    phase: "tool.execute",
    error: { message: "provider-looking tool error", reason: { _tag: "RateLimit", status: 429 } },
  })

  expect(result.kind).toBe("tool_execution_error")
  expect(result.source).toBe("tool")
  expect(result.producer).toBe("tool_host")
})

test("unstructured unknown text remains low-confidence and non-retryable", () => {
  const result = createFailureEnvelope({
    ...input,
    source: "model",
    error: new Error("정체를 알 수 없는 실패"),
  })

  expect(result.kind).toBe("unknown_failure")
  expect(result.classificationSource).toBe("heuristic")
  expect(result.confidence).toBe("low")
  expect(result.retryable).toBe(false)
})
