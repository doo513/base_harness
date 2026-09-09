import { expect, test } from "bun:test"
import { Coordinator } from "../../src/harness/coordinator-service"
import { tmpdir } from "../fixture/fixture"

const operations = [
  ["verifyRoot", (sessionID: string) => Coordinator.verifyRoot(sessionID, "manual")],
  ["verify", (sessionID: string) => Coordinator.verify({ sessionID, reason: "manual" })],
  ["cancel", (sessionID: string) => Coordinator.cancel(sessionID)],
] as const

for (const [name, operation] of operations) {
  test(name + " returns the current Kernel-enriched Host status without granting Ready", async () => {
    await using workspace = await tmpdir()
    const sessionID = "status-contract-" + name
    await Coordinator.control(sessionID, { type: "domain.set", domain: "general" }, undefined, workspace.path)
    await Coordinator.control(sessionID, { type: "planning.plan_once" })

    const result = await operation(sessionID)
    expect(result).toEqual(Coordinator.status(sessionID))
    expect(result).toMatchObject({
      sessionID,
      phase: "inactive",
      domain: "general",
      skills: [],
      planningPreference: "plan_once",
      planningState: "idle",
      readyEligible: false,
    })
  })
}

test("control responses, events and reads use the same Host status view", async () => {
  await using workspace = await tmpdir()
  const sessionID = "status-contract-events"
  const observed: unknown[] = []
  const unsubscribe = Coordinator.subscribe((status) => {
    if (status.sessionID === sessionID) observed.push(status)
  })
  try {
    const result = await Coordinator.control(sessionID, { type: "domain.set", domain: "general" }, undefined, workspace.path)
    expect(observed).toHaveLength(1)
    expect(observed[0]).toEqual(result)
    expect(result).toEqual(Coordinator.status(sessionID))
  } finally {
    unsubscribe()
  }
})


test("persistent control requires workspace without granting Ready on rejection", async () => {
  const sessionID = "status-contract-missing-workspace"
  await expect(Coordinator.control(sessionID, {
    type: "domain.set", domain: "general",
  })).rejects.toMatchObject({ code: "SESSION_WORKSPACE_REQUIRED" })
  expect(Coordinator.status(sessionID)).toMatchObject({
    phase: "inactive",
    readyEligible: false,
  })
})
