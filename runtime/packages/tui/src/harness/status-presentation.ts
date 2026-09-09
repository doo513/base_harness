export interface HarnessPresentationStatus {
  phase: string
  planningState?: string
  history?: { phase: string; readOnly: true; revalidated: false }
}

/** Render Host state; this function grants no execution or verification authority. */
export function harnessDisplayPhase(status: HarnessPresentationStatus): string {
  if (["blocked", "interrupted", "failure"].includes(status.phase)) return status.phase
  if (status.planningState && status.planningState !== "idle" && status.planningState !== "executing") {
    return status.planningState
  }
  if (status.phase === "inactive" && status.history) return "history_" + status.history.phase
  return status.phase
}

/** The execution marker persists after a run ends; display the Host phase, not an active plan. */
export function harnessLifecycleLabel(status: HarnessPresentationStatus): string {
  if (status.phase === "inactive" && status.history && (!status.planningState || status.planningState === "idle")) {
    return "History " + status.history.phase + " (not reverified)"
  }
  if (status.planningState === "executing") return `Execution ${harnessDisplayPhase(status)}`
  return `Planning ${status.planningState ?? "idle"}`
}
