import { expect, test } from "bun:test"
import { harnessDisplayPhase, harnessLifecycleLabel } from "../src/harness/status-presentation"

for (const planningState of [
  "contract_building", "contract_preflight", "contract_reviewing", "awaiting_input",
  "planning_decision", "plan_building", "plan_reviewing", "plan_ready",
]) {
  test("the footer exposes Kernel state instead of a stale direct phase: " + planningState, () => {
    expect(harnessDisplayPhase({ phase: "direct", planningState })).toBe(planningState)
  })
}

test("reviewed plans cannot be presented as verified completion", () => {
  expect(harnessDisplayPhase({ phase: "ready", planningState: "plan_ready" })).toBe("plan_ready")
})

for (const phase of ["worker_running", "integration", "root_verifying", "ready"]) {
  test("execution uses the Coordinator phase: " + phase, () => {
    expect(harnessDisplayPhase({ phase, planningState: "executing" })).toBe(phase)
  })
}

test("terminal failures remain visible even with unfinished Kernel planning state", () => {
  for (const phase of ["blocked", "interrupted", "failure"]) {
    expect(harnessDisplayPhase({ phase, planningState: "plan_reviewing" })).toBe(phase)
  }
})

for (const phase of ["worker_running", "integration", "root_verifying", "ready", "blocked", "interrupted", "failure"]) {
  test("plan execution details follow the Host phase: " + phase, () => {
    const status = Object.freeze({ phase, planningState: "executing" })
    expect(harnessLifecycleLabel(status)).toBe("Execution " + phase)
    expect(status.planningState).toBe("executing")
  })
}

test("lifecycle labels never turn a reviewed plan into execution or Ready", () => {
  expect(harnessLifecycleLabel({ phase: "ready", planningState: "plan_ready" })).toBe("Planning plan_ready")
  expect(harnessLifecycleLabel({ phase: "direct", planningState: "contract_reviewing" })).toBe("Planning contract_reviewing")
  expect(harnessLifecycleLabel({ phase: "inactive" })).toBe("Planning idle")
})
