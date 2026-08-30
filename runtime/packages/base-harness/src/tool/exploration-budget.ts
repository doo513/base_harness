export type ExplorationThoroughness = "quick" | "standard" | "deep"
export const EXPLORATION_ALLOWED_TOOLS = ["read", "grep", "glob", "list"] as const
export const EXPLORATION_DENIED_TOOLS = [
  "bash",
  "shell",
  "argv",
  "write",
  "edit",
  "apply_patch",
  "task",
  "webfetch",
  "websearch",
] as const

export interface ExplorationRequest {
  thoroughness: ExplorationThoroughness
  maxToolCalls?: number
  maxFiles?: number
}

export interface ExplorationBudgetStatus {
  request: Required<ExplorationRequest>
  toolCalls: number
  uniqueFiles: number
  truncated: boolean
  violations: number
}

const PRESETS: Record<ExplorationThoroughness, { maxToolCalls: number; maxFiles: number }> = {
  quick: { maxToolCalls: 8, maxFiles: 12 },
  standard: { maxToolCalls: 20, maxFiles: 40 },
  deep: { maxToolCalls: 50, maxFiles: 120 },
}

interface ExplorationBudgetState {
  request: Required<ExplorationRequest>
  toolCalls: number
  files: Set<string>
  truncated: boolean
  violations: number
}

const states = new Map<string, ExplorationBudgetState>()

export class ExplorationBudgetExceeded extends Error {
  readonly terminal: boolean
  readonly status: ExplorationBudgetStatus

  constructor(status: ExplorationBudgetStatus) {
    super(
      `exploration budget exhausted: toolCalls=${status.toolCalls}/${status.request.maxToolCalls}, files=${status.uniqueFiles}/${status.request.maxFiles}`,
    )
    this.name = "ExplorationBudgetExceeded"
    this.terminal = status.violations >= 2
    this.status = status
  }
}

export function normalizeExplorationRequest(request?: ExplorationRequest): Required<ExplorationRequest> {
  const thoroughness = request?.thoroughness ?? "standard"
  const preset = PRESETS[thoroughness]
  return {
    thoroughness,
    maxToolCalls: Math.max(1, Math.min(Math.floor(request?.maxToolCalls ?? preset.maxToolCalls), preset.maxToolCalls)),
    maxFiles: Math.max(1, Math.min(Math.floor(request?.maxFiles ?? preset.maxFiles), preset.maxFiles)),
  }
}

export function openExplorationBudget(sessionID: string, request?: ExplorationRequest) {
  const normalized = normalizeExplorationRequest(request)
  states.set(sessionID, {
    request: normalized,
    toolCalls: 0,
    files: new Set(),
    truncated: false,
    violations: 0,
  })
  return normalized
}

export function consumeExplorationBudget(sessionID: string, tool: string, filepath?: string) {
  const state = states.get(sessionID)
  if (!state) return

  if (state.truncated) {
    state.violations += 1
    throw new ExplorationBudgetExceeded(toStatus(state))
  }

  state.toolCalls += 1
  if (filepath) state.files.add(filepath)
  if (state.toolCalls > state.request.maxToolCalls || state.files.size > state.request.maxFiles) {
    state.truncated = true
    state.violations += 1
    throw new ExplorationBudgetExceeded(toStatus(state))
  }

  return toStatus(state)
}

export function explorationBudgetStatus(sessionID: string) {
  const state = states.get(sessionID)
  return state ? toStatus(state) : undefined
}

export function closeExplorationBudget(sessionID: string) {
  states.delete(sessionID)
}

export function explorationInstruction(request: Required<ExplorationRequest>) {
  return [
    "Return a partial ExplorationReport with truncated=true if either budget is exhausted.",
    `Exploration thoroughness: ${request.thoroughness}.`,
    `Maximum tool calls: ${request.maxToolCalls}.`,
    `Maximum unique files read: ${request.maxFiles}.`,
    `Only ${EXPLORATION_ALLOWED_TOOLS.join(", ")} are permitted.`,
  ].join("\n")
}

function toStatus(state: ExplorationBudgetState): ExplorationBudgetStatus {
  return {
    request: state.request,
    toolCalls: state.toolCalls,
    uniqueFiles: state.files.size,
    truncated: state.truncated,
    violations: state.violations,
  }
}
