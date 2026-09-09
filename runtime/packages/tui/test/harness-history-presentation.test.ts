import { expect, test } from "bun:test"
import { harnessDisplayPhase, harnessLifecycleLabel } from "../src/harness/status-presentation"

for (const phase of ["ready", "blocked", "failure", "interrupted", "plan_ready"]) {
  test("past " + phase + " is visibly historical and never current Ready", () => {
    const status = Object.freeze({
      phase: "inactive", planningState: "idle",
      history: { phase, readOnly: true as const, revalidated: false as const },
    })
    expect(harnessDisplayPhase(status)).toBe("history_" + phase)
    expect(harnessLifecycleLabel(status)).toBe("History " + phase + " (not reverified)")
    expect(status.phase).toBe("inactive")
  })
}

test("active planning and current terminal failures take precedence over stale presentation metadata", () => {
  const history = { phase: "ready", readOnly: true as const, revalidated: false as const }
  expect(harnessDisplayPhase({ phase: "planning", planningState: "contract_building", history })).toBe("contract_building")
  expect(harnessDisplayPhase({ phase: "blocked", planningState: "executing", history })).toBe("blocked")
  expect(harnessDisplayPhase({ phase: "ready", planningState: "executing", history })).toBe("ready")
  expect(harnessLifecycleLabel({ phase: "ready", planningState: "executing", history })).toBe("Execution ready")
})
