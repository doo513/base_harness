import { randomUUID } from "node:crypto"
import { ProviderError } from "../providers/types"
import { ToolExecutionError } from "../tools/types"
import { VerificationProtocolError } from "../verification/client"

export type FailureKind = "model_provider_error" | "model_protocol_error" | "tool_execution_error" | "implementation_error" | "workspace_conflict" | "verifier_error" | "harness_error" | "unknown_failure"
export interface FailureContext { runId: string; scopeId: string; actionId?: string; phase: string }

export function failureEnvelope(error: unknown, context: FailureContext): Record<string, unknown> {
  if (error instanceof ProviderError) {
    const protocol = error.code === "INVALID_PROVIDER_OUTPUT"
    return envelope(context, protocol ? "model_protocol_error" : "model_provider_error", protocol ? "model" : "provider", "model_gateway", error.code, error.status, error.retryable, error.message, error.details)
  }
  if (error instanceof ToolExecutionError) return envelope(context, "tool_execution_error", "tool", "tool_host", error.code, undefined, false, error.message, error.details)
  if (error instanceof VerificationProtocolError) return envelope(context, "verifier_error", "verifier", "verifier_sidecar", error.code, undefined, false, error.message)
  const message = error instanceof Error ? error.message : String(error)
  return envelope(context, "harness_error", "harness", "orchestrator", "UNHANDLED_HOST_ERROR", undefined, false, message)
}

function envelope(context: FailureContext, kind: FailureKind, source: string, producer: string, code: string, status: number | undefined, retryable: boolean, message: string, details?: unknown) {
  return {
    version: 1,
    id: randomUUID(),
    runId: context.runId,
    scopeId: context.scopeId,
    actionId: context.actionId,
    kind,
    source,
    producer,
    phase: context.phase,
    code,
    status,
    retryable,
    terminal: false,
    classificationSource: status === undefined ? "typed" : "status",
    confidence: "high",
    message,
    details,
  }
}
