export type BackendKind = "model_api" | "agent_runtime"

export interface BackendSelection {
  kind: BackendKind
  backendId: string
  connectionId: string
  modelId: string
  nativeOptions: Record<string, string>
  capabilityRevision: string
}

export interface BackendModelInfo {
  modelId: string
  reasoningEfforts: string[]
  defaultReasoningEffort?: string
}

export interface BackendCapabilities {
  adapterID: string
  backendId: string
  kind: BackendKind
  revision: string
  models: string[]
  reasoningEfforts: string[]
  reasoningOption?: string
  modelDetails?: BackendModelInfo[]
  /** Explicit opt-in. Backends without this contract never receive autonomous Runs. */
  autonomousDecision?: {
    protocol: "autonomous-decision-v1"
    resourceUsage: "reported-v1"
  }
}

export type BackendMutationPolicy = "forbid" | "capture"

export interface BackendExecutionInput {
  sessionID: string
  runId?: string
  scopeID?: string
  phase?: "contract" | "plan" | "implementation" | "repair" | "meta_review" | string
  workspace: string
  prompt: string
  selection: BackendSelection
  /** Controls whether changes made inside a managed backend workspace are published. */
  mutationPolicy?: BackendMutationPolicy
  signal?: AbortSignal
  routeWrite: (relativePath: string) => Promise<{ physicalPath: string }>
}

export interface BackendExecutionResult {
  output: string
  changedFiles: string[]
  capabilityRevision: string
  backendId: string
  modelId: string
  nativeOptions: Record<string, string>
  /** Required when autonomousDecision.resourceUsage is reported-v1. */
  resourceUsage?: { modelTokens: number; costMinorUnits: number }
}

export interface ExecutionBackend {
  readonly id: string
  readonly kind: BackendKind
  selectionFromEnvironment?(): unknown
  discover(): Promise<BackendCapabilities>
  execute(input: BackendExecutionInput): Promise<BackendExecutionResult>
}

export class BackendExecutionError extends Error {
  constructor(
    readonly code:
      | "BACKEND_UNAVAILABLE"
      | "BACKEND_AUTH_REQUIRED"
      | "BACKEND_CAPABILITY_STALE"
      | "BACKEND_MODEL_UNAVAILABLE"
      | "BACKEND_OPTION_UNSUPPORTED"
      | "BACKEND_PROTOCOL_ERROR"
      | "BACKEND_RUN_FAILED"
      | "BACKEND_SCOPE_VIOLATION",
    message: string,
    readonly details?: unknown,
  ) {
    super(message)
    this.name = "BackendExecutionError"
  }
}

export function normalizeBackendSelection(input: unknown): BackendSelection | undefined {
  if (!input || typeof input !== "object") return
  const value = input as Record<string, unknown>
  const backendId = typeof value.backendId === "string"
    ? value.backendId
    : typeof value.adapterID === "string"
      ? value.adapterID
      : undefined
  const modelId = typeof value.modelId === "string"
    ? value.modelId
    : typeof value.modelID === "string"
      ? value.modelID
      : undefined
  if (!backendId || !modelId) return
  const options = value.nativeOptions ?? value.options
  const nativeOptions: Record<string, string> = {}
  if (options && typeof options === "object") {
    for (const [key, option] of Object.entries(options)) {
      if (typeof option === "string") nativeOptions[key] = option
    }
  }
  return Object.freeze({
    kind: value.kind === "model_api" ? "model_api" : "agent_runtime",
    backendId,
    connectionId: typeof value.connectionId === "string" ? value.connectionId : backendId,
    modelId,
    nativeOptions: Object.freeze(nativeOptions),
    capabilityRevision: typeof value.capabilityRevision === "string" ? value.capabilityRevision : "",
  })
}
