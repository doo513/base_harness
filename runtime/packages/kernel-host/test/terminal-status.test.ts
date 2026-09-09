import { afterEach, beforeEach, expect, test } from "bun:test"
import { mkdtemp, mkdir, realpath, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { KernelHost } from "../src"

let scratch: string
let workspace: string
beforeEach(async () => {
  scratch = await mkdtemp(path.join(os.tmpdir(), "base-harness-terminal-status-"))
  workspace = path.join(scratch, "workspace")
  await mkdir(workspace)
})
afterEach(async () => {
  const parent = await realpath(os.tmpdir())
  const actual = await realpath(scratch)
  if (path.dirname(actual) !== parent || !path.basename(actual).startsWith("base-harness-terminal-status-")) {
    throw new Error("Unsafe scratch cleanup")
  }
  await rm(actual, { recursive: true, force: true })
})

function fixture() {
  let current: any = { sessionID: "session", runId: "", phase: "inactive", readyEligible: false }
  const runtime = {
    status: () => current,
    openRun: async () => current = {
      ...current, workspace, runId: "run", phase: "planning", contractStatus: "missing",
    },
    proposeContract: async () => current = { ...current, contractStatus: "accepted" },
    acceptWorkGraph: async () => { throw new Error("Unexpected worker dispatch") },
    beginDirect: () => { current = { ...current, phase: "direct" } },
  }
  const host = new KernelHost(runtime, { directory: path.join(scratch, "plans") })
  return { host, set: (value: Record<string, unknown>) => { current = { ...current, ...value } } }
}

const contract = () => ({
  interpretation: { version: 1, candidates: [] },
  criteria: [{ criterionId: "criterion", claimIds: ["claim"], required: true, risk: "low" }],
  claims: [{
    claimId: "claim", criterionIds: ["criterion"], required: true,
    applicability: { status: "applicable" }, verifierPolicy: { minimumEvidenceFamilies: 1 },
  }],
})

for (const phase of ["ready", "blocked", "failure", "interrupted"]) {
  test("terminal " + phase + " presentation does not revoke Kernel admission", async () => {
    const { host, set } = fixture()
    await host.openRun({ sessionID: "session", workspace, goal: "Update one file" })
    expect(host.canVerifyRoot("session")).toBe(false)
    await host.proposeContract("session", contract())
    expect(host.status("session").planningState).toBe("executing")
    expect(host.canVerifyRoot("session")).toBe(true)
    set({ phase, outcome: phase, readyEligible: phase === "ready" })
    const status = host.status("session")
    expect(status.planningState).toBe("idle")
    expect(status.phase).toBe(phase)
    expect(status.outcome).toBe(phase)
    expect(status.readyEligible).toBe(phase === "ready")
    expect((await host.readStatus("session", workspace)).planningState).toBe("idle")
    // This is admission, not permission to bypass the Coordinator's terminal/run gates.
    expect(host.canVerifyRoot("session")).toBe(true)
    set({ phase: "root_verifying", outcome: undefined, readyEligible: false })
    expect(host.status("session").planningState).toBe("executing")
    expect(host.canVerifyRoot("session")).toBe(true)
  })
}

test("runtime presentation fields cannot grant Kernel admission", async () => {
  const { host, set } = fixture()
  set({ phase: "ready", planningState: "executing", readyEligible: true })
  expect(host.canVerifyRoot("session")).toBe(false)
  expect(host.status("session").planningState).toBe("idle")
  await host.openRun({ sessionID: "session", workspace, goal: "New request" })
  const status = host.status("session")
  status.planningState = "executing"
  expect(host.canVerifyRoot("session")).toBe(false)
})

test("plan-only contract remains pending and cannot grant execution admission", async () => {
  const { host } = fixture()
  await host.control("session", { type: "planning.plan_once" })
  await host.openRun({ sessionID: "session", workspace, goal: "Plan one file update" })
  await host.proposeContract("session", contract())
  expect(host.status("session").planningState).toBe("planning_decision")
  expect(host.status("session").planOnly).toBe(true)
  expect(host.canVerifyRoot("session")).toBe(false)
  expect(() => host.assertToolAllowed("session", "edit")).toThrow("PLAN_ONLY_MUTATION_DENIED")
})
