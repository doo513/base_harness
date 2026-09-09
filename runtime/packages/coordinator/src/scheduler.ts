import type { WorkUnit, WorkerState } from "./contracts"

export interface SchedulableWorker {
  workUnitId: string
  state: WorkerState
  unit: WorkUnit
}

export const dependenciesComplete = <T extends SchedulableWorker>(
  worker: T,
  workers: ReadonlyMap<string, T>,
) => worker.unit.dependsOn.every((id) => workers.get(id)?.state === "completed")

export const nextRunnable = <T extends SchedulableWorker>(workers: ReadonlyMap<string, T>) =>
  [...workers.values()].find((worker) => worker.state === "queued" && dependenciesComplete(worker, workers))

export const hasPendingWork = <T extends SchedulableWorker>(
  workers: ReadonlyMap<string, T>,
  activeCount: number,
  integrationStarted: boolean,
  integrationComplete: boolean,
  outcome?: string,
) => {
  if (activeCount > 0) return true
  if ([...workers.values()].some((worker) => ["running", "candidate_ready", "verifying", "committing", "repairing"].includes(worker.state))) return true
  const integrationSettled = integrationComplete || outcome === "blocked" || outcome === "failure"
    || outcome === "repair_exhausted" || outcome === "needs_input"
  if (integrationStarted && !integrationSettled) return true
  if (workers.size && [...workers.values()].every((worker) => worker.state === "completed")) return !integrationSettled
  return [...workers.values()].some((worker) => worker.state === "queued" && dependenciesComplete(worker, workers))
}
