import { expect, test } from "bun:test"
import { KernelHost } from "../src"

const proposal = () => ({
  goal: "create result.txt",
  criteria: [{ criterionId: "criterion", statement: "result exists", claimIds: ["claim"], required: true, risk: "low" }],
  claims: [{
    claimId: "claim", criterionIds: ["criterion"], origin: "user", kind: "artifact", statement: "result exists",
    scope: { targets: ["result.txt"], capabilities: ["write"], exclusions: [] },
    applicability: { status: "resolved", os: "any" }, predicate: { type: "exists" },
    verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
  }],
  interpretation: { version: 1, candidates: [] },
})

function fixture(accept: boolean, terminal: { phase?: string; outcome?: string } = {}) {
  let direct = 0
  const runtime = {
    openRun: async () => ({ runId: "run", configuredProfile: "adaptive", phase: "planning" }),
    proposeContract: async () => ({ runId: "run", contractStatus: accept ? "accepted" : "missing", outcome: accept ? undefined : "failure", ...terminal }),
    acceptWorkGraph: async () => { throw new Error("Atomic work must not create a WorkGraph") },
    status: () => ({ runId: "run", configuredProfile: "adaptive", phase: "planning" }),
    beginDirect: () => { direct += 1 },
  }
  return { host: new KernelHost(runtime), direct: () => direct }
}

test("accepted atomic contract reaches direct execution without a WorkGraph", async () => {
  const { host, direct } = fixture(true)
  await host.openRun({ sessionID: "atomic", workspace: ".", goal: "create result.txt" })
  const state = await host.proposeContract("atomic", proposal())
  expect(state.planningDecision).toBe("direct")
  expect(state.planningState).toBe("executing")
  expect(direct()).toBe(1)
  expect(state.preflight.reviewerCallCount).toBe(0)
})

test("rejected contract never opens direct execution or mutation", async () => {
  const { host, direct } = fixture(false)
  await host.openRun({ sessionID: "rejected", workspace: ".", goal: "create result.txt" })
  const state = await host.proposeContract("rejected", proposal())
  expect(state.planningState).toBe("contract_building")
  expect(state.contractStatus).toBe("missing")
  expect(state.outcome).toBe("failure")
  expect(state.preflight.mutatingActionAllowed).toBe(false)
  expect(direct()).toBe(0)
  expect(() => host.assertToolAllowed("rejected", "edit")).toThrow()
})

test("plan-only accepted contract cannot reach direct execution", async () => {
  const { host, direct } = fixture(true)
  await host.control("planned", { type: "planning.plan_once" })
  await host.openRun({ sessionID: "planned", workspace: ".", goal: "create result.txt" })
  const state = await host.proposeContract("planned", proposal())
  expect(state.planningDecision).toBe("planned")
  expect(direct()).toBe(0)
  expect(() => host.assertToolAllowed("planned", "edit")).toThrow()
})

test("missing interpretation is not silently treated as no uncertainty", async () => {
  const { host } = fixture(true)
  await host.openRun({ sessionID: "missing", workspace: ".", goal: "create result.txt" })
  const { interpretation: _, ...missing } = proposal()
  await expect(host.proposeContract("missing", missing)).rejects.toBeInstanceOf(Error)
})

for (const terminal of [
  { phase: "blocked" },
  { phase: "interrupted" },
  { phase: "failure" },
  { outcome: "failure" },
]) {
  test("an accepted contract cannot authorize a terminal run: " + JSON.stringify(terminal), async () => {
    const { host, direct } = fixture(true, terminal)
    await host.openRun({ sessionID: "blocked", workspace: ".", goal: "create result.txt" })
    await expect(host.proposeContract("blocked", proposal())).rejects.toThrow("PLAN_RUN_BLOCKED")
    const state = host.status("blocked")
    expect(state.planningState).not.toBe("executing")
    expect(state.preflight.mutatingActionAllowed).toBe(false)
    expect(direct()).toBe(0)
    expect(() => host.assertToolAllowed("blocked", "edit")).toThrow()
  })
}
