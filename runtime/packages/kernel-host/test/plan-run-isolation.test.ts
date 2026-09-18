import { expect, spyOn, test } from "bun:test"
import { mkdir, mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { KernelHost } from "../src"
import { ReviewedPlanStore } from "../src/reviewed-plan-store"
import { contractFixture } from "./contract-fixture"

const contract = contractFixture({
  goal: "Update requested artifact",
  criteria: [{ criterionId: "criterion", claimIds: ["claim"], risk: "low" }],
  claims: [{ claimId: "claim", criterionIds: ["criterion"], applicability: { status: "resolved" } }],
})
const graph = (instruction: string) => ({
  units: [{ id: "unit", title: instruction, instructions: instruction, claimIds: ["claim"],
    criterionIds: ["criterion"], dependsOn: [], readSet: [], writeSet: ["input.ts"], integrationRequests: [] }],
  integrationPaths: [],
})

async function fixture(body: (value: {
  host: KernelHost; adapter: any; workspace: string; directory: string;
  dispatch: any[]; failures: unknown[];
}) => Promise<void>, planOnly = false) {
  const root = await mkdtemp(join(tmpdir(), "host-plan-isolation-"))
  const workspace = join(root, "workspace"), directory = join(root, "plans")
  await mkdir(workspace)
  let current: any = { sessionID: "root", runId: "", phase: "inactive" }, sequence = 0
  const dispatch: any[] = [], failures: unknown[] = []
  const adapter = {
    status: () => current,
    openRun: async () => current = { ...current, runId: `run-${++sequence}`, phase: "planning", contractStatus: "missing" },
    proposeContract: async () => current = { ...current, contractStatus: "accepted" },
    beginPlanning: () => current = { ...current, phase: "planning" },
    beginDirect: () => current = { ...current, phase: "direct" },
    acceptWorkGraph: async () => { throw new Error("Use run-bound dispatch") },
    submitDomainProposal: async (input: any) => { dispatch.push(input); return current },
    cancel: async () => current = { ...current, phase: "interrupted" },
    reportMetaReviewFailure: async (...args: unknown[]) => { failures.push(args); return current },
  }
  const host = new KernelHost(adapter, { directory })
  await host.control("root", { type: "skill.set", skill: "hackathon", enabled: true })
  if (planOnly) await host.control("root", { type: "planning.plan_once" })
  await host.openRun({ sessionID: "root", workspace, goal: contract.goal })
  await host.proposeContract("root", contract)
  try { await body({ host, adapter, workspace, directory, dispatch, failures }) }
  finally { await rm(root, { recursive: true, force: true }) }
}

for (const result of ["pass", "revise", "reject"] as const) {
  test(`a late ${result} plan reviewer cannot change a replacement Run`, async () => {
    await fixture(async ({ host, adapter, workspace, directory, dispatch, failures }) => {
      const entered = Promise.withResolvers<void>(), release = Promise.withResolvers<void>()
      host.registerMetaReviewer(async (request) => {
        entered.resolve()
        await release.promise
        if (result === "reject") throw new Error("old reviewer transport failure")
        return { phase: request.phase, outcome: result, issues: [] }
      })
      const old = host.acceptWorkGraph("root", graph("OLD RUN INSTRUCTION")).catch((error) => error)
      await entered.promise
      await adapter.cancel()
      await host.openRun({ sessionID: "root", workspace, goal: "New request" })
      await host.proposeContract("root", contract)
      const before = structuredClone(host.status("root"))
      release.resolve()
      expect(await old).toHaveProperty("code", "PLAN_RUN_CHANGED")
      expect(host.status("root")).toEqual(before)
      expect(dispatch).toHaveLength(0)
      expect(failures).toHaveLength(0)
      expect(await new ReviewedPlanStore({ directory }).findPending("root")).toBeUndefined()
    })
  })
}

test("cancelled plan review cannot publish a plan even without a replacement Run", async () => {
  await fixture(async ({ host, adapter, directory, dispatch, failures }) => {
    const entered = Promise.withResolvers<void>(), release = Promise.withResolvers<void>()
    host.registerMetaReviewer(async () => { entered.resolve(); await release.promise; return { phase: "plan", outcome: "pass", issues: [] } })
    const old = host.acceptWorkGraph("root", graph("old")).catch((error) => error)
    await entered.promise
    await adapter.cancel()
    release.resolve()
    expect(await old).toHaveProperty("code", "PLAN_RUN_CHANGED")
    expect(dispatch).toHaveLength(0)
    expect(failures).toHaveLength(0)
    expect(await new ReviewedPlanStore({ directory }).findPending("root")).toBeUndefined()
  })
})

test("a newer contract invalidates a pending plan review in the same Run", async () => {
  await fixture(async ({ host, dispatch }) => {
    const entered = Promise.withResolvers<void>(), release = Promise.withResolvers<void>()
    host.registerMetaReviewer(async () => { entered.resolve(); await release.promise; return { phase: "plan", outcome: "pass", issues: [] } })
    const old = host.acceptWorkGraph("root", graph("old")).catch((error) => error)
    await entered.promise
    await host.proposeContract("root", { ...contract, goal: "Changed request" })
    const before = structuredClone(host.status("root"))
    release.resolve()
    expect(await old).toHaveProperty("code", "PLAN_RUN_CHANGED")
    expect(host.status("root")).toEqual(before)
    expect(dispatch).toHaveLength(0)
  })
})

test("a newer graph invalidates a pending review in the same Run", async () => {
  await fixture(async ({ host, dispatch }) => {
    const entered = Promise.withResolvers<void>(), release = Promise.withResolvers<void>()
    let calls = 0
    host.registerMetaReviewer(async () => {
      if (++calls === 1) { entered.resolve(); await release.promise }
      return { phase: "plan", outcome: "pass", issues: [] }
    })
    const old = host.acceptWorkGraph("root", graph("old")).catch((error) => error)
    await entered.promise
    await host.acceptWorkGraph("root", graph("current"))
    const before = structuredClone(host.status("root"))
    release.resolve()
    expect(await old).toHaveProperty("code", "PLAN_RUN_CHANGED")
    expect(host.status("root")).toEqual(before)
    expect(dispatch.map((value) => value.proposal.graph.units[0].instructions)).toEqual(["current"])
  })
})

for (const planOnly of [false, true]) {
  test(`cancellation during publication retires only the old plan before new Run admission (planOnly=${planOnly})`, async () => {
    await fixture(async ({ host, adapter, workspace, directory, dispatch, failures }) => {
      host.registerMetaReviewer(async () => ({ phase: "plan", outcome: "pass", issues: [] }))
      const entered = Promise.withResolvers<void>(), release = Promise.withResolvers<void>()
      const save = ReviewedPlanStore.prototype.save
      const delayed = spyOn(ReviewedPlanStore.prototype, "save").mockImplementation(async function (this: ReviewedPlanStore, record, revision) {
        const saved = await save.call(this, record, revision)
        entered.resolve()
        await release.promise
        return saved
      })
      try {
        const old = host.acceptWorkGraph("root", graph("old")).catch((error) => error)
        await entered.promise
        await adapter.cancel()
        const next = host.openRun({ sessionID: "root", workspace, goal: "New request" })
        expect(adapter.status().runId).toBe("run-1")
        release.resolve()
        expect(await old).toHaveProperty("code", "PLAN_RUN_CHANGED")
        expect((await next).runId).toBe("run-2")
        expect(dispatch).toHaveLength(0)
        expect(failures).toHaveLength(0)
        expect(await new ReviewedPlanStore({ directory }).findPending("root")).toBeUndefined()
        expect(host.status("root").activePlanId).toBeUndefined()
      } finally { release.resolve(); delayed.mockRestore() }
    }, planOnly)
  })
}

test("new Run admission notices a publication that starts during its status read", async () => {
  await fixture(async ({ host, adapter, workspace, directory, dispatch }) => {
    host.registerMetaReviewer(async () => ({ phase: "plan", outcome: "pass", issues: [] }))
    const reading = Promise.withResolvers<void>(), releaseRead = Promise.withResolvers<void>()
    const saving = Promise.withResolvers<void>(), releaseSave = Promise.withResolvers<void>()
    const read = host.readStatus.bind(host)
    const delayedRead = spyOn(host, "readStatus").mockImplementation(async (...args) => {
      const value = await read(...args)
      reading.resolve()
      await releaseRead.promise
      return value
    })
    const save = ReviewedPlanStore.prototype.save
    const delayedSave = spyOn(ReviewedPlanStore.prototype, "save").mockImplementation(async function (this: ReviewedPlanStore, record, revision) {
      const value = await save.call(this, record, revision)
      saving.resolve()
      await releaseSave.promise
      return value
    })
    const open = adapter.openRun
    let saveReleased = false
    const admission = spyOn(adapter, "openRun").mockImplementation(async () => {
      expect(saveReleased).toBe(true)
      return open()
    })
    try {
      const next = host.openRun({ sessionID: "root", workspace, goal: "New request" }).catch((error) => error)
      await reading.promise
      const old = host.acceptWorkGraph("root", graph("old")).catch((error) => error)
      await saving.promise
      await adapter.cancel()
      releaseRead.resolve()
      // The openRun spy asserts the durable boundary itself, without sleeps.
      await Promise.resolve()
      await Promise.resolve()
      saveReleased = true
      releaseSave.resolve()
      expect(await old).toHaveProperty("code", "PLAN_RUN_CHANGED")
      expect((await next).runId).toBe("run-2")
      expect(dispatch).toHaveLength(0)
      expect(await new ReviewedPlanStore({ directory }).findPending("root")).toBeUndefined()
    } finally {
      releaseRead.resolve(); releaseSave.resolve()
      delayedRead.mockRestore(); delayedSave.mockRestore(); admission.mockRestore()
    }
  })
})
