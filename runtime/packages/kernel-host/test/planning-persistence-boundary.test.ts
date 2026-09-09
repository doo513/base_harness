import { expect, test } from "bun:test"
import { promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"
import { KernelHost } from "../src"

async function temporary() {
  return fs.mkdtemp(path.join(os.tmpdir(), "base-harness-phase34-"))
}
async function cleanup(directory: string) {
  const resolved = path.resolve(directory)
  if (path.dirname(resolved) !== path.resolve(os.tmpdir()) || !path.basename(resolved).startsWith("base-harness-phase34-")) {
    throw new Error("Refusing cleanup outside the test scratch directory")
  }
  await fs.rm(resolved, { recursive: true, force: true })
}

function runtime() {
  let serial = 0
  let executions = 0
  let graphs = 0
  const current = { sessionID: "s1", runId: "", phase: "inactive", contractStatus: "missing" }
  return {
    current,
    get executions() { return executions },
    get graphs() { return graphs },
    openRun: async () => {
      Object.assign(current, { runId: "run-" + ++serial, phase: "planning", contractStatus: "missing" })
      return { ...current }
    },
    proposeContract: async () => { current.contractStatus = "accepted"; return { ...current } },
    acceptWorkGraph: async () => { graphs++; current.phase = "scheduling"; return { ...current } },
    beginPlanExecution: async () => { executions++; current.runId = "execute-" + serial; return { ...current } },
    cancel: async () => { current.runId = ""; current.phase = "inactive"; return { ...current } },
    status: () => ({ ...current, readyEligible: false }),
  }
}
const proposal = {
  interpretation: { version: 1, candidates: [] },
  criteria: [{ criterionId: "criterion-1", claimIds: ["claim-1"], required: true, risk: "low" }],
  claims: [{ claimId: "claim-1", criterionIds: ["criterion-1"], required: true,
    applicability: { status: "applicable" }, verifierPolicy: { minimumEvidenceFamilies: 1 } }],
}
const graph = {
  units: [{ id: "unit-1", title: "Change input", instructions: "Change only input.ts",
    claimIds: ["claim-1"], criterionIds: ["criterion-1"], dependsOn: [],
    readSet: ["input.ts"], writeSet: ["input.ts"], integrationRequests: [] }],
  integrationPaths: [],
}
async function plan(host: KernelHost, workspace: string) {
  await host.control("s1", { type: "planning.plan_once" })
  await host.openRun({ sessionID: "s1", workspace, goal: "change input", defaultDomain: "develop" })
  await host.proposeContract("s1", proposal)
  return host.acceptWorkGraph("s1", graph)
}

test("a persistence failure during plan review cannot advance to plan_ready", async () => {
  const directory = await temporary()
  const workspace = path.join(directory, "workspace")
  const adapter = runtime()
  const host = new KernelHost(adapter, { directory: path.join(directory, "plans") })
  host.registerMetaReviewer(async request => {
    if (request.phase === "plan") adapter.current.phase = "blocked"
    return { phase: request.phase, outcome: "pass", issues: [] }
  })
  try {
    await fs.mkdir(workspace)
    await fs.writeFile(path.join(workspace, "input.ts"), "export const value = 1\n")
    await expect(plan(host, workspace)).rejects.toThrow("PLAN_RUN_BLOCKED")
    expect(host.status("s1").planningState).not.toBe("plan_ready")
    expect(host.status("s1").readyEligible).toBe(false)
    expect(adapter.graphs).toBe(0)
    expect(adapter.executions).toBe(0)
  } finally { await cleanup(directory) }
})

test("a blocked reviewed plan is rejected before preparation or consumption and remains discardable", async () => {
  const directory = await temporary()
  const workspace = path.join(directory, "workspace")
  const adapter = runtime()
  const host = new KernelHost(adapter, { directory: path.join(directory, "plans") })
  host.registerMetaReviewer(async request => ({ phase: request.phase, outcome: "pass", issues: [] }))
  try {
    await fs.mkdir(workspace)
    await fs.writeFile(path.join(workspace, "input.ts"), "export const value = 1\n")
    const reviewed = await plan(host, workspace)
    adapter.current.phase = "blocked"
    await expect(host.preparePlanExecution("s1", workspace, reviewed.activePlanId)).rejects.toThrow("PLAN_RUN_BLOCKED")
    await expect(host.control("s1", { type: "planning.execute", planId: reviewed.activePlanId })).rejects.toThrow("PLAN_RUN_BLOCKED")
    expect((await host.resolvePlan(reviewed.activePlanId)).planId).toBe(reviewed.activePlanId)
    expect(adapter.executions).toBe(0)
    const discarded = await host.control("s1", { type: "planning.discard" })
    expect(discarded.activePlanId).toBeUndefined()
    expect(discarded.planningState).toBe("idle")
  } finally { await cleanup(directory) }
})

test("restoring and discarding a reviewed plan preserves the selected hackathon skill", async () => {
  const directory = await temporary()
  const workspace = path.join(directory, "workspace"), plans = path.join(directory, "plans")
  const first = new KernelHost(runtime(), { directory: plans })
  first.registerMetaReviewer(async request => ({ phase: request.phase, outcome: "pass", issues: [] }))
  try {
    await fs.mkdir(workspace)
    await fs.writeFile(path.join(workspace, "input.ts"), "export const value = 1\n")
    await first.control("s1", { type: "skill.set", skill: "hackathon", enabled: true })
    await plan(first, workspace)
    const restored = new KernelHost(runtime(), { directory: plans })
    expect((await restored.readStatus("s1", workspace)).skills).toEqual(["hackathon"])
    await restored.control("s1", { type: "planning.discard" })
    const next = await restored.openRun({
      sessionID: "s1", workspace, goal: "another request", defaultDomain: "develop",
    })
    expect(next.domain).toBe("develop")
    expect(next.skills).toEqual(["hackathon"])
  } finally { await cleanup(directory) }
})
