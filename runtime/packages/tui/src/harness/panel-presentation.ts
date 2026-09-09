export function harnessPanelLayout(columns: number, rows: number) {
  const cols = Math.max(1, Math.floor(Number.isFinite(columns) ? columns : 80))
  const lines = Math.max(1, Math.floor(Number.isFinite(rows) ? rows : 24))
  const width = Math.max(1, Math.min(64, cols - 4))
  const height = Math.max(1, lines - 3)
  return {
    width,
    height,
    contentWidth: Math.max(1, width - 4),
    bodyHeight: Math.max(0, height - 4),
  }
}

export interface HarnessPlanningPresentation {
  sessionID?: string
  phase?: string
  planningPreference?: "auto" | "plan_once"
  planningState?: string
  planOnly?: boolean
  planRecovery?: { code: string }
}

export function nextRequestPlanOnly(status: HarnessPlanningPresentation, stagedPlanOnce: boolean) {
  if (!status.sessionID) return stagedPlanOnce
  return (status.planningState === undefined || status.planningState === "idle")
    && status.planningPreference === "plan_once"
}

const activePlanningStates = new Set([
  "contract_building", "contract_preflight", "contract_reviewing", "awaiting_input",
  "planning_decision", "plan_building", "plan_reviewing",
])
const terminalPhases = new Set(["ready", "blocked", "interrupted", "failure"])

export function harnessPlanningCue(status: HarnessPlanningPresentation, stagedPlanOnce: boolean) {
  if (status.planRecovery) {
    return {
      kind: "recovery" as const,
      label: "/plan discard to recover",
      message: "Plan revision pending or interrupted. Use /plan discard, then build a new plan.",
    }
  }
  if (status.sessionID && status.planningState === "plan_ready"
      && ["blocked", "interrupted", "failure"].includes(status.phase ?? "")) {
    return {
      kind: "blocked" as const,
      label: "plan execution blocked",
      message: "The plan was reviewed, but the Host run is blocked. Resolve the failure and rebuild the plan before execution.",
    }
  }
  if (status.sessionID && status.planningState === "plan_ready") {
    return {
      kind: "reviewed" as const,
      label: "reviewed: /execute to start",
      message: "Plan reviewed. Use /execute to start; no Ready has been issued.",
    }
  }
  if (status.sessionID && status.planOnly && activePlanningStates.has(status.planningState ?? "")
      && !terminalPhases.has(status.phase ?? "")) {
    return {
      kind: "active" as const,
      label: "planning: plan-only",
      message: "Plan-only in progress. Implementation waits for a reviewed plan and /execute.",
    }
  }
  if (nextRequestPlanOnly(status, stagedPlanOnce)) {
    return {
      kind: "next" as const,
      label: "next: plan-only",
      message: "Next request: plan-only. Use /execute after the plan is reviewed.",
    }
  }
}
