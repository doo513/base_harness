import { AntigravityCli } from "./antigravity-cli"
import {
  BackendExecutionError,
  normalizeBackendSelection,
  type BackendCapabilities,
  type BackendExecutionInput,
  type BackendExecutionResult,
  type ExecutionBackend,
} from "./backend"
import { CodexAppServer } from "./codex-app-server"

const antigravityBackend: ExecutionBackend = {
  id: AntigravityCli.id,
  kind: "agent_runtime",
  selectionFromEnvironment: () => AntigravityCli.selectionFromEnvironment(),
  async discover() {
    const capabilities = await AntigravityCli.capabilities()
    return {
      ...capabilities,
      backendId: capabilities.adapterID,
      kind: "agent_runtime",
      reasoningOption: "reasoning_effort",
      autonomousDecision: { protocol: "autonomous-decision-v1", resourceUsage: "reported-v1" },
    } satisfies BackendCapabilities
  },
  async execute(input: BackendExecutionInput): Promise<BackendExecutionResult> {
    const result = await AntigravityCli.execute({
      sessionID: input.scopeID ?? input.sessionID,
      workspace: input.workspace,
      prompt: input.prompt,
      modelID: input.selection.modelId,
      options: input.selection.nativeOptions,
      capabilityRevision: input.selection.capabilityRevision,
      phase: input.phase,
      mutationPolicy: input.mutationPolicy,
      signal: input.signal,
      routeWrite: input.routeWrite,
    })
    return {
      output: result.output,
      changedFiles: result.changedFiles,
      capabilityRevision: result.capabilityRevision,
      backendId: AntigravityCli.id,
      modelId: input.selection.modelId,
      nativeOptions: input.selection.nativeOptions,
      ...(result.resourceUsage ? { resourceUsage: result.resourceUsage } : {}),
    }
  },
}

export class BackendRouter {
  private readonly backends = new Map<string, ExecutionBackend>()

  constructor(backends: ExecutionBackend[] = [antigravityBackend, CodexAppServer]) {
    for (const backend of backends) this.register(backend)
  }

  get(id: string) {
    return this.backends.get(id)
  }

  register(backend: ExecutionBackend) {
    const current = this.backends.get(backend.id)
    if (current && current !== backend) throw new Error("BACKEND_ALREADY_REGISTERED: " + backend.id)
    this.backends.set(backend.id, Object.freeze(backend))
    return this
  }

  async discover(id: string) {
    const backend = this.get(id)
    if (!backend) throw new BackendExecutionError("BACKEND_UNAVAILABLE", "Unknown execution backend: " + id)
    return backend.discover()
  }

  selectionFromEnvironment() {
    for (const backend of this.backends.values()) {
      const selection = normalizeBackendSelection(backend.selectionFromEnvironment?.())
      if (selection) return selection
    }
    return undefined
  }

  async execute(input: BackendExecutionInput) {
    const backend = this.get(input.selection.backendId)
    if (!backend) throw new BackendExecutionError("BACKEND_UNAVAILABLE", "Unknown execution backend: " + input.selection.backendId)
    return backend.execute(input)
  }
}

export const ExecutionBackends = new BackendRouter()
export { normalizeBackendSelection }
