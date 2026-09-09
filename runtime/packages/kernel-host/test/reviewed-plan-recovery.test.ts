import { expect, test } from "bun:test"
import { lstat, mkdtemp, mkdir, readFile, readdir, rename, writeFile, rm } from "node:fs/promises"
import { writeAtomicSnapshot } from "@base-harness/workspace/snapshot-persistence"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import { KernelHost } from "../src"
import { ReviewedPlanStore, type ReviewedPlanStoreOptions } from "../src/reviewed-plan-store"

let runSequence = 0

function runtime() {
  let status: any = { sessionID: "root", runId: "", phase: "inactive", readyEligible: false }
  const calls = { opened: 0, openInputs: [] as any[], restored: [] as any[], graphs: [] as any[], reviews: 0 }
  const host = {
    openRun: async (input: any) => {
      calls.opened++
      calls.openInputs.push(input)
      return status = { ...status, runId: "planning-run-" + (++runSequence), workspace: input.workspace, phase: "planning" }
    },
    proposeContract: async () => status = { ...status, contractStatus: "accepted" },
    acceptWorkGraph: async (_id: string, graph: any, context: any) => {
      calls.graphs.push({ graph, context })
      return status = { ...status, phase: "scheduling" }
    },
    beginPlanExecution: async () => status = { ...status, runId: "live-execution", contractStatus: "accepted" },
    beginRestoredPlanExecution: async (_id: string, input: any) => {
      calls.restored.push(input)
      return status = { ...status, runId: "fresh-execution", phase: "planning", contractStatus: "accepted" }
    },
    cancel: async () => status = { ...status, phase: "interrupted", readyEligible: false },
    status: () => status,
  }
  return { host, calls }
}

async function fixture(body: (value: {
  directory: string; workspace: string; plans: string; planned: any; host: KernelHost;
  policy: ReviewedPlanStoreOptions; saved: Awaited<ReturnType<ReviewedPlanStore["load"]>>;
}) => Promise<void>, options: Omit<ReviewedPlanStoreOptions, "directory"> & { hackathon?: boolean } = {}) {
  const directory = await mkdtemp(join(tmpdir(), "harness-reviewed-plan-"))
  const workspace = join(directory, "workspace"), plans = join(directory, "plans")
  await mkdir(workspace)
  await writeFile(join(workspace, "input.ts"), "export const value = 1\n")
  const { hackathon = true, ...storeOptions } = options
  const policy = { directory: plans, ...storeOptions }
  const base = runtime(), host = new KernelHost(base.host, policy)
  host.registerMetaReviewer(async request => {
    base.calls.reviews++
    return { phase: request.phase, outcome: "pass", issues: [] }
  })
  try {
    if (hackathon) await host.control("root", { type: "skill.set", skill: "hackathon", enabled: true })
    await host.control("root", { type: "planning.plan_once" })
    await host.openRun({ sessionID: "root", workspace, goal: "Update the module" })
    await host.proposeContract("root", {
      interpretation: { version: 1, candidates: [] },
      criteria: [{ criterionId: "criterion", claimIds: ["claim"], statement: "Update module", required: true, risk: "low" }],
      claims: [{ claimId: "claim", criterionIds: ["criterion"], statement: "Update module", required: true,
        applicability: { status: "applicable" }, scope: { targets: ["input.ts"] }, verifierPolicy: { minIndependentFamilies: 1 } }],
    })
    const context = { sessionID: "root", messageID: "assistant-plan", agent: "build",
      extra: { modelSelection: { providerID: "fixture", modelID: "reasoner" }, variant: "native-exact",
        promptOps: { mustNotPersist: () => {} }, credential: "never-save-this" } }
    const planned = await host.acceptWorkGraph("root", { units: [{
      id: "unit", title: "Update module", instructions: "Keep the approved instructions", agentType: "general",
      claimIds: ["claim"], criterionIds: ["criterion"], dependsOn: [], readSet: ["input.ts"], writeSet: ["input.ts"],
      integrationRequests: [],
    }], integrationPaths: [] }, context)
    const saved = await new ReviewedPlanStore(policy).load({ sessionID: "root" })
    await body({ directory, workspace, plans, planned, host, policy, saved })
  } finally {
    const rel = relative(tmpdir(), directory)
    if (rel.startsWith("..") || isAbsolute(rel)) throw new Error("Unsafe test cleanup")
    await rm(directory, { recursive: true, force: true })
  }
}

test("a fresh Host restores a reviewed plan without reviving execution or rerunning reviews", async () => {
  await fixture(async ({ workspace, planned, policy, saved }) => {
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    expect(host.status("root").planningState).toBe("idle")
    const location = await host.resolvePlan(planned.activePlanId)
    expect(location).toMatchObject({ sessionID: "root", workspace, revision: 1 })
    const selected = await host.preparePlanExecution("root", workspace, planned.activePlanId)
    expect(selected.selection.variant).toBe("native-exact")
    expect(host.status("root").planningState).toBe("plan_ready")
    expect(host.status("root").readyEligible).toBe(false)
    expect(fresh.calls.opened).toBe(0)
    expect(fresh.calls.restored).toHaveLength(0)
    expect(() => host.assertToolAllowed("root", "write")).toThrow("PLAN_ONLY_MUTATION_DENIED")
    const authority = { freshRequest: true }
    const executed = await host.control("root", { type: "planning.execute", planId: planned.activePlanId }, authority)
    expect(executed.runId).toBe("fresh-execution")
    expect(executed.skills).toEqual(["hackathon"])
    expect(fresh.calls.restored).toHaveLength(1)
    expect(fresh.calls.restored[0].planningRunId).toBe(planned.runId)
    expect(fresh.calls.restored[0].contract).toEqual(saved.contract)
    expect(fresh.calls.graphs[0].context.freshRequest).toBe(true)
    expect(fresh.calls.reviews).toBe(0)
  })
})

test("opaque context, provider options and credentials never enter the saved recipe", async () => {
  await fixture(async ({ plans, planned, saved }) => {
    const contents = await readFile(join(plans, planned.activePlanId, "reviewed.json"), "utf8")
    expect(contents).not.toContain("never-save-this")
    expect(contents).not.toContain("promptOps")
    expect(contents).not.toContain("freshRequest")
    expect(saved.selection).toEqual({
      providerID: "fixture", modelID: "reasoner", variant: "native-exact", agent: "build", messageID: "assistant-plan",
    })
  })
})

test("a changed basis or a different workspace cannot open an execution run", async () => {
  await fixture(async ({ directory, workspace, planned, policy }) => {
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    const other = join(directory, "other")
    await mkdir(other)
    await expect(host.preparePlanExecution("root", other, planned.activePlanId)).rejects.toThrow("PLAN_WORKSPACE_MISMATCH")
    await writeFile(join(workspace, "input.ts"), "external change\n")
    await expect(host.preparePlanExecution("root", workspace, planned.activePlanId)).rejects.toThrow("PLAN_STALE")
    expect(fresh.calls.restored).toHaveLength(0)
  })
})

test("tampering with the canonical plan is not accepted as a reviewed revision", async () => {
  await fixture(async ({ plans, planned, workspace, policy }) => {
    const canonical = join(plans, planned.activePlanId, "1.json")
    const value = JSON.parse(await readFile(canonical, "utf8"))
    value.workGraph.units[0].instructions = "Unreviewed replacement"
    await writeFile(canonical, JSON.stringify(value))
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    await expect(host.preparePlanExecution("root", workspace, planned.activePlanId)).rejects.toThrow("PLAN_INTEGRITY_INVALID")
    expect(fresh.calls.restored).toHaveLength(0)
  })
})

test("a replacement recipe cannot forge review provenance by keeping its old signature", async () => {
  await fixture(async ({ plans, planned, workspace, policy }) => {
    const file = join(plans, planned.activePlanId, "reviewed.json")
    const value = JSON.parse(await readFile(file, "utf8"))
    value.body.selection.variant = "invented-effort"
    await writeFile(file, JSON.stringify(value))
    await expect(new KernelHost(runtime().host, policy).preparePlanExecution("root", workspace, planned.activePlanId))
      .rejects.toThrow("PLAN_INTEGRITY_INVALID")
  })
})

test("only one process may consume a plan revision, and interruption cannot silently replay it", async () => {
  await fixture(async ({ policy, saved, workspace, planned }) => {
    const store = new ReviewedPlanStore(policy)
    const results = await Promise.allSettled([store.consume(saved, "execute"), store.consume(saved, "execute")])
    expect(results.filter(result => result.status === "fulfilled")).toHaveLength(1)
    expect(results.filter(result => result.status === "rejected")).toHaveLength(1)
    await expect(new KernelHost(runtime().host, policy).preparePlanExecution("root", workspace, planned.activePlanId))
      .rejects.toThrow("PLAN_ALREADY_CONSUMED")
  })
})

test("discarded plans and plans invalidated by a domain change stay unavailable after restart", async () => {
  for (const control of [{ type: "planning.discard" as const }, { type: "domain.set" as const, domain: "general" as const }]) {
    await fixture(async ({ host, policy, workspace, planned }) => {
      await host.control("root", control)
      await expect(new KernelHost(runtime().host, policy).preparePlanExecution("root", workspace, planned.activePlanId))
        .rejects.toThrow("PLAN_ALREADY_CONSUMED")
    })
  }
})

test("a persistence redactor cannot silently change the reviewed contract", async () => {
  await fixture(async ({ plans, saved }) => {
    const store = new ReviewedPlanStore({ directory: plans, redact: <T>(_runId: string, value: T): T =>
      JSON.parse(JSON.stringify(value).replaceAll("Update the module", "[REDACTED]")) as T })
    await expect(store.save(saved)).rejects.toThrow("PLAN_SECRET_REDACTION_REQUIRED")
  })
})

test("readStatus hydrates a cold pending plan without starting or publishing execution", async () => {
  await fixture(async ({ workspace, planned, policy }) => {
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    const events: unknown[] = []
    host.subscribe(status => events.push(status))
    const [first, second] = await Promise.all([host.readStatus("root", workspace), host.readStatus("root", workspace)])
    expect(first).toEqual(second)
    expect(first).toMatchObject({
      runId: planned.runId, workspace, goal: "Update the module", phase: "plan_ready",
      planningState: "plan_ready", planOnly: true, activePlanId: planned.activePlanId,
      activePlanRevision: 1, skills: ["hackathon"], verificationState: "inactive", readyEligible: false,
    })
    expect(first.goalContract).toEqual(planned.goalContract)
    expect(first.plan).toEqual(planned.plan)
    expect(fresh.calls).toMatchObject({ opened: 0, restored: [], graphs: [], reviews: 0 })
    expect(events).toHaveLength(0)
    expect(() => host.assertToolAllowed("root", "write")).toThrow("PLAN_ONLY_MUTATION_DENIED")
  })
})

test("an absent plan pointer is read-only and does not create a store", async () => {
  await fixture(async ({ directory, workspace }) => {
    const absent = join(directory, "absent-plans")
    const host = new KernelHost(runtime().host, { directory: absent })
    expect(await host.readStatus("new-session", workspace)).toMatchObject({
      phase: "inactive", planningState: "idle", planOnly: false,
    })
    await expect(lstat(absent)).rejects.toHaveProperty("code", "ENOENT")
  })
})

test("cold status rejects another workspace without starting a run", async () => {
  await fixture(async ({ directory, policy }) => {
    const other = join(directory, "other")
    await mkdir(other)
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    await expect(host.readStatus("root", other)).rejects.toThrow("PLAN_WORKSPACE_MISMATCH")
    expect(fresh.calls.opened).toBe(0)
    expect(fresh.calls.restored).toHaveLength(0)
  })
})

test("missing or corrupt referenced recipes cannot silently become ordinary direct work", async () => {
  for (const damage of ["missing", "tampered"] as const) {
    await fixture(async ({ plans, planned, workspace, policy }) => {
      const canonical = join(plans, planned.activePlanId, "1.json")
      if (damage === "missing") await rm(canonical)
      else await writeFile(canonical, "{}")
      const fresh = runtime(), host = new KernelHost(fresh.host, policy)
      await expect(host.readStatus("root", workspace)).rejects.toThrow()
      await expect(host.openRun({ sessionID: "root", workspace, goal: "Continue" })).rejects.toThrow()
      expect(fresh.calls.opened).toBe(0)
    })
  }
})

test("executed and discarded plans are not displayed as pending after restart", async () => {
  for (const reason of ["execute", "discard"] as const) {
    await fixture(async ({ saved, workspace, policy }) => {
      await new ReviewedPlanStore(policy).consume(saved, reason)
      const fresh = runtime(), host = new KernelHost(fresh.host, policy)
      expect(await host.readStatus("root", workspace)).toMatchObject({
        phase: "inactive", planningState: "idle", planOnly: false,
      })
      expect(fresh.calls.restored).toHaveLength(0)
    })
  }
})

test("pending revision status is read-only and requires explicit discard before another request", async () => {
  await fixture(async ({ saved, workspace, policy }) => {
    await new ReviewedPlanStore(policy).consume(saved, "revise")
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    const events: unknown[] = []
    host.subscribe(status => events.push(status))
    expect(await host.readStatus("root", workspace)).toMatchObject({
      phase: "blocked", planningState: "awaiting_input", planOnly: true, readyEligible: false,
      planRecovery: { code: "PLAN_REVISION_PENDING", action: "planning.discard",
        planId: saved.plan.planId, revision: 1 },
    })
    await expect(host.openRun({ sessionID: "root", workspace, goal: "Continue" }))
      .rejects.toThrow("PLAN_REVISION_PENDING")
    await expect(host.control("root", { type: "planning.execute" })).rejects.toThrow("PLAN_REVISION_PENDING")
    await expect(host.control("root", { type: "domain.set", domain: "general" })).rejects.toThrow("PLAN_REVISION_PENDING")
    expect(() => host.assertToolAllowed("root", "write")).toThrow("PLAN_ONLY_MUTATION_DENIED")
    expect(fresh.calls.opened).toBe(0)
    expect(fresh.calls.graphs).toHaveLength(0)
    expect(events).toHaveLength(0)
    expect(await host.control("root", { type: "planning.discard" })).toMatchObject({
      planningState: "idle", planOnly: false, readyEligible: false,
    })
    await host.openRun({ sessionID: "root", workspace, goal: "A new request" })
    expect(fresh.calls.openInputs[0].revisesPlan).toBeUndefined()
    expect(fresh.calls.openInputs[0].goal).toBe("A new request")
    await expect(new ReviewedPlanStore(policy).load({ planId: saved.plan.planId })).rejects.toThrow("PLAN_ALREADY_CONSUMED")
  })
})

test("an ordinary atomic revision stays plan-only before the WorkGraph even without plan_once", async () => {
  await fixture(async ({ saved, workspace, policy }) => {
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    host.registerMetaReviewer(async request => ({ phase: request.phase, outcome: "pass", issues: [] }))
    await host.openRun({ sessionID: "root", workspace, goal: "Refine this plan" })
    expect(fresh.calls.openInputs[0].revisesPlan).toEqual({
      planningRunId: saved.plan.runId, planId: saved.plan.planId,
      planRevision: saved.plan.revision, goalContractHash: saved.plan.goalContractHash,
    })
    expect(host.status("root").planningPreference).toBe("auto")
    const accepted = await host.proposeContract("root", {
      ...(saved.contract as Record<string, unknown>), interpretation: { version: 1, candidates: [] },
    })
    expect(accepted).toMatchObject({ planningDecision: "planned", planningState: "planning_decision", planOnly: true })
    expect(() => host.assertToolAllowed("root", "write")).toThrow("PLAN_ONLY_MUTATION_DENIED")
    expect(() => host.assertToolAllowed("root", "bash")).toThrow("PLAN_ONLY_MUTATION_DENIED")
    const revised = await host.acceptWorkGraph("root", saved.plan.workGraph, {
      sessionID: "root", agent: "build", messageID: "assistant-revision",
      extra: { modelSelection: { providerID: "fixture", modelID: "reasoner" }, variant: "native-exact" },
    })
    expect(revised).toMatchObject({
      planningState: "plan_ready", planOnly: true, activePlanId: saved.plan.planId, activePlanRevision: 2,
    })
    expect(fresh.calls.graphs).toHaveLength(0)
    expect(fresh.calls.restored).toHaveLength(0)
    const next = new KernelHost(runtime().host, policy)
    expect(await next.readStatus("root", workspace)).toMatchObject({ planOnly: true, activePlanRevision: 2 })
    await next.control("root", { type: "planning.discard" })
    expect(next.status("root").planOnly).toBe(false)
  }, { hackathon: false })
})

test("cold domain controls invalidate the persisted plan rather than ignoring it", async () => {
  await fixture(async ({ workspace, policy }) => {
    const host = new KernelHost(runtime().host, policy)
    const status = await host.control("root", { type: "domain.set", domain: "general" })
    expect(status.domain).toBe("general")
    expect(await new KernelHost(runtime().host, policy).readStatus("root", workspace))
      .toMatchObject({ planningState: "idle", planOnly: false })
  })
})

function successor(saved: Awaited<ReturnType<ReviewedPlanStore["load"]>>) {
  return {
    ...structuredClone(saved),
    goal: "A newly reviewed request",
    plan: { ...structuredClone(saved.plan), revision: saved.plan.revision + 1, runId: "new-reviewed-run" },
    state: { ...structuredClone(saved.state), activePlanRevision: saved.plan.revision + 1 },
  }
}

test("a discarded revision cannot be published later by its previous owner", async () => {
  await fixture(async ({ saved, workspace, policy }) => {
    const store = new ReviewedPlanStore(policy)
    const claim = await store.consume(saved, "revise")
    const host = new KernelHost(runtime().host, policy)
    await host.readStatus("root", workspace)
    await host.control("root", { type: "planning.discard" })
    await expect(store.save(successor(saved), claim)).rejects.toThrow("PLAN_REVISION_DISCARDED")
    expect(await store.findPending("root")).toBeUndefined()
    await store.discardRevision(saved)
    await expect(store.load({ sessionID: "root" })).rejects.toThrow("PLAN_ALREADY_CONSUMED")
  })
})

test("publication and discard have exactly one durable winner", async () => {
  await fixture(async ({ saved, policy }) => {
    const store = new ReviewedPlanStore(policy)
    const claim = await store.consume(saved, "revise")
    const result = await Promise.allSettled([store.save(successor(saved), claim), store.discardRevision(saved)])
    expect(result.filter(item => item.status === "fulfilled")).toHaveLength(1)
    expect(result.filter(item => item.status === "rejected")).toHaveLength(1)
    if (result[0]!.status === "fulfilled") {
      expect((await store.load({ sessionID: "root" })).plan.revision).toBe(2)
    } else {
      expect(await store.findPending("root")).toBeUndefined()
      await expect(store.load({ sessionID: "root" })).rejects.toThrow("PLAN_ALREADY_CONSUMED")
    }
  })
})

test("a signed publication recovers even when the latest-head cache was not updated", async () => {
  await fixture(async ({ saved, plans, policy }) => {
    const store = new ReviewedPlanStore(policy)
    const file = join(plans, saved.plan.planId, "reviewed.json")
    const oldHead = await readFile(file, "utf8")
    const claim = await store.consume(saved, "revise")
    const published = await store.save(successor(saved), claim)
    await writeFile(file, oldHead)
    expect(await store.load({ sessionID: "root" })).toEqual(published)
    await expect(store.discardRevision(saved)).rejects.toThrow("PLAN_SUPERSEDED")
  })
})

test("a cold pending preview refreshes to the published revision without executing it", async () => {
  await fixture(async ({ saved, workspace, policy }) => {
    const store = new ReviewedPlanStore(policy)
    const claim = await store.consume(saved, "revise")
    const fresh = runtime(), host = new KernelHost(fresh.host, policy)
    expect((await host.readStatus("root", workspace)).planRecovery).toBeDefined()
    await store.save(successor(saved), claim)
    expect(await host.readStatus("root", workspace)).toMatchObject({
      planningState: "plan_ready", activePlanRevision: 2, planOnly: true, readyEligible: false,
    })
    expect(host.status("root").planRecovery).toBeUndefined()
    expect(fresh.calls.opened).toBe(0)
    expect(fresh.calls.restored).toHaveLength(0)
  })
})

test("legacy interrupted revision markers can be discarded but not resumed as execution", async () => {
  await fixture(async ({ saved, workspace, plans, policy }) => {
    await writeFile(join(plans, saved.plan.planId, "1.consumed.json"),
      JSON.stringify({ reason: "revise", timestamp: "2026-09-07T00:00:00.000Z" }))
    const host = new KernelHost(runtime().host, policy)
    expect((await host.readStatus("root", workspace)).planRecovery).toBeDefined()
    await expect(host.preparePlanExecution("root", workspace, saved.plan.planId)).rejects.toThrow("PLAN_ALREADY_CONSUMED")
    await host.control("root", { type: "planning.discard" })
    expect(await new ReviewedPlanStore(policy).findPending("root")).toBeUndefined()
  })
})

test("revision ownership and signed resolution integrity are both required", async () => {
  await fixture(async ({ saved, plans, policy }) => {
    const store = new ReviewedPlanStore(policy)
    const claim = await store.consume(saved, "revise")
    await expect(store.save(successor(saved), { ...claim, token: "wrong-owner" }))
      .rejects.toThrow("PLAN_REVISION_CLAIM_INVALID")
    await store.discardRevision(saved)
    const file = join(plans, saved.plan.planId, "1.resolution.json")
    const value = JSON.parse(await readFile(file, "utf8"))
    value.body.reason = "publish"
    value.body.next = successor(saved)
    await writeFile(file, JSON.stringify(value))
    await expect(store.findPending("root")).rejects.toThrow("PLAN_INTEGRITY_INVALID")
  })
})

test("discarding a live reviewed plan closes its run and the next plan has fresh identity", async () => {
  await fixture(async ({ saved, workspace, planned, host, policy }) => {
    await host.control("root", { type: "planning.discard" })
    await host.control("root", { type: "planning.plan_once" })
    await host.openRun({ sessionID: "root", workspace, goal: "A different plan" })
    await host.proposeContract("root", {
      ...(saved.contract as Record<string, unknown>), interpretation: { version: 1, candidates: [] },
    })
    const next = await host.acceptWorkGraph("root", saved.plan.workGraph, {
      sessionID: "root", agent: "build", messageID: "new-plan",
      extra: { modelSelection: { providerID: "fixture", modelID: "reasoner" } },
    })
    expect(next).toMatchObject({ planningState: "plan_ready", activePlanRevision: 1, planOnly: true })
    expect(next.activePlanId).not.toBe(planned.activePlanId)
    expect(next.runId).not.toBe(planned.runId)
    expect((await new ReviewedPlanStore(policy).load({ sessionID: "root" })).goal).toBe("A different plan")
  })
})

test("a Windows head-cache rename retry preserves bytes until the signed revision is published", async () => {
  await fixture(async ({ saved, plans, policy }) => {
    const head = join(plans, saved.plan.planId, "reviewed.json")
    const previous = await readFile(head, "utf8")
    let attempts = 0
    const delays: number[] = []
    const store = new ReviewedPlanStore(policy, (file, body) => writeAtomicSnapshot(file, body, {
      platform: "win32",
      sleep: async milliseconds => { delays.push(milliseconds) },
      rename: async (source, destination) => {
        if (destination === head) {
          expect(await readFile(head, "utf8")).toBe(previous)
          if (++attempts < 3) throw Object.assign(new Error("Injected file lock"), { code: "EPERM" })
        }
        await rename(source, destination)
      },
    }))
    const claim = await store.consume(saved, "revise")
    const published = await store.save(successor(saved), claim)
    expect(attempts).toBe(3)
    expect(delays).toEqual([10, 25])
    expect(await store.load({ sessionID: "root" })).toEqual(published)
    expect((await readdir(join(plans, saved.plan.planId))).filter(name => name.endsWith(".tmp"))).toEqual([])
  })
})

test("a permanently locked head cache remains intact and the signed revision remains recoverable", async () => {
  await fixture(async ({ saved, plans, policy }) => {
    const head = join(plans, saved.plan.planId, "reviewed.json")
    const previous = await readFile(head, "utf8")
    let attempts = 0
    const store = new ReviewedPlanStore(policy, (file, body) => writeAtomicSnapshot(file, body, {
      platform: "win32",
      sleep: async () => {},
      rename: async (source, destination) => {
        if (destination === head) {
          attempts++
          throw Object.assign(new Error("Injected persistent lock"), { code: "EPERM" })
        }
        await rename(source, destination)
      },
    }))
    const claim = await store.consume(saved, "revise")
    await expect(store.save(successor(saved), claim)).rejects.toHaveProperty("code", "EPERM")
    expect(attempts).toBe(6)
    expect(await readFile(head, "utf8")).toBe(previous)
    expect((await new ReviewedPlanStore(policy).load({ sessionID: "root" })).plan.revision).toBe(2)
    expect((await readdir(join(plans, saved.plan.planId))).filter(name => name.endsWith(".tmp"))).toEqual([])
  })
})

test("a failed canonical write cannot publish or execute an incomplete revision", async () => {
  await fixture(async ({ saved, plans, policy }) => {
    const canonical = join(plans, saved.plan.planId, "2.json")
    let attempts = 0
    const store = new ReviewedPlanStore(policy, (file, body) => writeAtomicSnapshot(file, body, {
      platform: "win32",
      sleep: async () => {},
      rename: async (source, destination) => {
        if (destination === canonical) {
          attempts++
          throw Object.assign(new Error("Injected persistent lock"), { code: "EPERM" })
        }
        await rename(source, destination)
      },
    }))
    const claim = await store.consume(saved, "revise")
    await expect(store.save(successor(saved), claim)).rejects.toHaveProperty("code", "EPERM")
    expect(attempts).toBe(6)
    await expect(lstat(canonical)).rejects.toHaveProperty("code", "ENOENT")
    expect(await store.findPending("root")).toMatchObject({ state: "revision_pending", record: { plan: { revision: 1 } } })
    await expect(store.load({ sessionID: "root" })).rejects.toThrow("PLAN_ALREADY_CONSUMED")
    expect((await readdir(join(plans, saved.plan.planId))).filter(name => name.endsWith(".tmp"))).toEqual([])
    await store.discardRevision(saved)
    expect(await store.findPending("root")).toBeUndefined()
  })
})

test("an invalidated snapshot writer cannot be treated as a published plan", async () => {
  await fixture(async ({ saved, policy }) => {
    const store = new ReviewedPlanStore(policy, async () => false)
    const claim = await store.consume(saved, "revise")
    await expect(store.save(successor(saved), claim)).rejects.toThrow("PLAN_STORE_WRITE_INVALIDATED")
    expect((await store.findPending("root"))?.state).toBe("revision_pending")
    await store.discardRevision(saved)
  })
})
