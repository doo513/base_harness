import { expect, test } from "bun:test"
import { KernelHost } from "../src"

function fixture() {
  const transitions: string[] = []
  let dispatched = 0
  const runtime = {
    openRun: async () => ({ runId: "run", phase: "direct", configuredProfile: "adaptive" }),
    proposeContract: async () => ({ runId: "run", phase: "direct", contractStatus: "accepted" }),
    acceptWorkGraph: async () => { dispatched++; return {} },
    beginDirect: () => { transitions.push("direct") },
    beginPlanning: () => { transitions.push("planning") },
    status: () => ({ runId: "run", phase: "direct", configuredProfile: "adaptive" }),
  }
  return { host: new KernelHost(runtime), transitions, dispatched: () => dispatched }
}

function proposal() {
  return {
    goal: "Produce one file",
    criteria: [{ criterionId: "criterion", statement: "Output exists", claimIds: ["claim"], required: true, risk: "low" }],
    claims: [{
      claimId: "claim", criterionIds: ["criterion"], origin: "user", statement: "Output exists", kind: "artifact",
      scope: { targets: ["output.txt"], capabilities: ["write"], exclusions: [] },
      applicability: { os: process.platform },
      predicate: { type: "exists" },
      verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
    }],
    interpretation: { version: 1, candidates: [] },
  }
}

test("typed plan-only selection moves the workspace from direct to planning", async () => {
  const { host, transitions } = fixture()
  await host.control("root", { type: "planning.plan_once" })
  await host.openRun({ sessionID: "root", workspace: process.cwd(), goal: "Produce one file" })
  const result = await host.proposeContract("root", proposal())
  expect(result.planningDecision).toBe("planned")
  expect(result.planningState).toBe("planning_decision")
  expect(transitions).toEqual(["planning"])
  expect(() => host.assertToolAllowed("root", "write")).toThrow()
})

test("an atomic direct request does not dispatch an unnecessary WorkGraph", async () => {
  const { host, transitions, dispatched } = fixture()
  await host.openRun({ sessionID: "root", workspace: process.cwd(), goal: "Produce one file" })
  await host.proposeContract("root", proposal())
  const result = await host.acceptWorkGraph("root", {
    units: [{
      id: "unit", title: "Output", instructions: "Produce output.txt",
      claimIds: ["claim"], criterionIds: ["criterion"], dependsOn: [],
      readSet: [], writeSet: ["output.txt"], integrationRequests: [],
    }],
    integrationPaths: [],
  })
  expect(result.planningDecision).toBe("direct")
  expect(result.planningState).toBe("executing")
  expect(transitions).toEqual(["direct", "direct"])
  expect(dispatched()).toBe(0)
})
