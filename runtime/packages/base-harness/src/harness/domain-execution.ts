import type { DomainExecutionDispatcher } from "./coordinator-service"
import { BackendExecutionError } from "./execution/backend"
import { ExecutionBackends, normalizeBackendSelection } from "./execution/backend-router"

/**
 * Stable application adapter for run-bound Domain requests. The binding selects
 * the backend for each request; no session installs or replaces a global callback.
 */
export const dispatchDomainExecution: DomainExecutionDispatcher = async (request) => {
  request.signal.throwIfAborted()
  if (request.proposal.dispatch !== "adapter") {
    throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Attached execution cannot be dispatched by an adapter")
  }
  if (request.proposal.mutationPolicy !== "forbid") {
    throw new BackendExecutionError(
      "BACKEND_SCOPE_VIOLATION",
      "Direct external mutation is unsupported; Develop changes must use a WorkGraph Candidate",
    )
  }
  const executor = request.binding.executor
  const selection = normalizeBackendSelection({
    kind: executor.kind,
    backendId: executor.id,
    connectionId: executor.connectionId ?? executor.id,
    modelId: executor.modelId,
    nativeOptions: executor.options,
    capabilityRevision: executor.revision,
  })
  if (!selection || !ExecutionBackends.get(selection.backendId)) {
    throw new BackendExecutionError("BACKEND_UNAVAILABLE", "Unknown execution backend: " + executor.id)
  }
  const result = await ExecutionBackends.execute({
    sessionID: request.sessionID,
    runId: request.runId,
    scopeID: request.sessionID,
    phase: request.preparation.mode === "read" ? "research" : "implementation",
    workspace: request.workspace,
    prompt: JSON.stringify({
      protocol: "base-harness-domain-execution-v1",
      runId: request.runId,
      domain: request.binding.selection.domain,
      goal: request.goal,
      instructions: request.preparation.instructions,
      request: request.proposal.instruction,
      constraints: {
        mutationPolicy: request.proposal.mutationPolicy,
        noEvidenceOrReadyAuthority: true,
      },
    }),
    selection,
    mutationPolicy: "forbid",
    signal: request.signal as AbortSignal,
    routeWrite: async () => {
      throw new BackendExecutionError("BACKEND_SCOPE_VIOLATION", "Direct Domain execution is read-only")
    },
  })
  request.signal.throwIfAborted()
  return {
    runId: request.runId,
    output: result.output,
    changedFiles: [...result.changedFiles],
    adapterId: result.backendId,
    modelId: result.modelId,
  }
}
