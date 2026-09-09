import { expect, test } from "bun:test"
import { hasPendingWork, type SchedulableWorker } from "../src/scheduler"

function worker(id: string, state: SchedulableWorker["state"], dependsOn: string[] = []): SchedulableWorker {
  return {
    workUnitId: id, state,
    unit: {
      id, title: id, instructions: "fixture", claimIds: ["claim-" + id], criterionIds: ["criterion-" + id],
      dependsOn, readSet: [id + ".txt"], writeSet: [id + ".txt"], integrationRequests: [],
    },
  }
}

for (const outcome of ["blocked", "failure", "repair_exhausted", "needs_input"]) {
  test("terminal root integration does not leave a phantom completion wait: " + outcome, () => {
    const workers = new Map([["a", worker("a", "completed")], ["b", worker("b", "completed")]])
    expect(hasPendingWork(workers, 0, true, false, outcome)).toBe(false)
    expect(hasPendingWork(workers, 1, true, false, outcome)).toBe(true)
  })
}

for (const state of ["running", "candidate_ready", "verifying", "committing", "repairing"] as const) {
  test("in-flight work still prevents early settlement: " + state, () => {
    const workers = new Map([["a", worker("a", state)]])
    expect(hasPendingWork(workers, 0, true, false, "blocked")).toBe(true)
  })
}

test("queued independent work remains pending while failed dependencies alone do not", () => {
  const failed = worker("a", "repair_exhausted")
  expect(hasPendingWork(new Map([["a", failed], ["b", worker("b", "queued")]]), 0, false, false, "blocked")).toBe(true)
  expect(hasPendingWork(new Map([["a", failed], ["b", worker("b", "queued", ["a"])]]), 0, false, false, "blocked")).toBe(false)
})

test("successful or repairing integration remains pending until the executor actually finishes", () => {
  const workers = new Map([["a", worker("a", "completed")]])
  expect(hasPendingWork(workers, 0, false, false)).toBe(true)
  expect(hasPendingWork(workers, 0, true, false)).toBe(true)
  expect(hasPendingWork(workers, 0, true, false, "repair")).toBe(true)
  expect(hasPendingWork(workers, 0, true, true, "ready")).toBe(false)
})
