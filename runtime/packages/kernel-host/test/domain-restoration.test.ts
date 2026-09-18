import { expect, test } from "bun:test"
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import {
  builtinDomainResolver, developExecutionModule, generalExecutionModule,
  hackathonExecutionOverlay, DomainExecutionRegistry, DomainRegistry,
} from "@base-harness/domain"
import { KernelHost } from "../src"
import { ReviewedPlanStore } from "../src/reviewed-plan-store"
import { contractFixture } from "./contract-fixture"

function runtime() {
  let current: any = { sessionID: "root", runId: "", phase: "inactive", readyEligible: false }
  const calls = { opened: 0, handoffs: [] as any[], graphs: [] as any[] }
  return {
    calls,
    openRun: async (input: any) => {
      calls.opened++
      return current = { ...current, runId: "planning", phase: "planning", workspace: input.workspace }
    },
    proposeContract: async () => current = { ...current, contractStatus: "accepted" },
    acceptWorkGraph: async (_id: string, graph: any) => { calls.graphs.push(graph); return current },
    beginPlanExecution: async (_id: string, input: any) => {
      calls.handoffs.push(input)
      return current = { ...current, runId: "execution", phase: "planning", contractStatus: "accepted" }
    },
    beginRestoredPlanExecution: async (_id: string, input: any) => {
      calls.handoffs.push(input)
      return current = { ...current, runId: "restored-execution", phase: "planning", contractStatus: "accepted" }
    },
    cancel: async () => current = { ...current, phase: "interrupted" },
    status: () => current,
  }
}

async function fixture(body: (input: {
  root: string; workspace: string; directory: string; host: KernelHost; adapter: ReturnType<typeof runtime>;
  planId: string; options: { directory: string; domainExecutions?: DomainExecutionRegistry };
}) => Promise<void>, domainExecutions?: DomainExecutionRegistry) {
  const root = await mkdtemp(join(tmpdir(), "harness-domain-restoration-"))
  const workspace = join(root, "workspace"), directory = join(root, "plans")
  await mkdir(workspace)
  await writeFile(join(workspace, "input.ts"), "export const value = 1\n")
  const adapter = runtime(), options = { directory, domainExecutions }
  const host = new KernelHost(adapter, options)
  host.registerMetaReviewer(async (request) => ({ phase: request.phase, outcome: "pass", issues: [] }))
  try {
    await host.control("root", { type: "skill.set", skill: "hackathon", enabled: true })
    await host.control("root", { type: "planning.plan_once" })
    await host.openRun({ sessionID: "root", workspace, goal: "Update input.ts" })
    await host.proposeContract("root", contractFixture({
      goal: "Update input.ts",
      criteria: [{ criterionId: "criterion", claimIds: ["claim"], risk: "low" }],
      claims: [{ claimId: "claim", criterionIds: ["criterion"], applicability: { status: "resolved" } }],
    }))
    const planned = await host.acceptWorkGraph("root", {
      units: [{ id: "unit", title: "Change input", instructions: "Approved instructions", agentType: "general",
        claimIds: ["claim"], criterionIds: ["criterion"], dependsOn: [], readSet: ["input.ts"],
        writeSet: ["input.ts"], integrationRequests: [] }],
      integrationPaths: [],
    })
    await body({ root, workspace, directory, host, adapter, planId: planned.activePlanId, options })
  } finally {
    await rm(root, { recursive: true, force: true })
  }
}

test("a saved domain recipe is passive until explicit execution rebinds the same strategies", async () => {
  await fixture(async ({ workspace, directory, planId, options }) => {
    const saved = await new ReviewedPlanStore({ directory }).load({ planId })
    expect(saved.domainBinding).toMatchObject({
      schemaVersion: "plan-domain-binding-v1",
      selection: { domain: "develop", skills: ["hackathon"] },
      module: { id: "develop-default", revision: "1" },
      overlays: [{ overlayId: "hackathon", overlayRevision: "hackathon-1" }],
    })
    expect(saved.domainBinding).not.toHaveProperty("executor")
    expect(saved.domainBinding).not.toHaveProperty("runId")
    const adapter = runtime(), host = new KernelHost(adapter, options)
    const preview = await host.readStatus("root", workspace)
    expect(preview.planningState).toBe("plan_ready")
    expect(preview.domainBinding).toBeUndefined()
    expect(preview.readyEligible).toBe(false)
    expect(adapter.calls.opened).toBe(0)
    expect(adapter.calls.handoffs).toHaveLength(0)
    const executed = await host.control("root", { type: "planning.execute", planId })
    expect(executed.domainBinding.runId).toBe("restored-execution")
    expect(adapter.calls.handoffs).toHaveLength(1)
    expect(adapter.calls.graphs).toEqual([saved.plan.workGraph])
  })
})

for (const change of ["domain-revision", "policy", "skill-reference", "overlay-revision", "strategy", "missing-overlay"] as const) {
  test(`restoration rejects ${change} drift before consuming or executing the reviewed plan`, async () => {
    await fixture(async ({ workspace, directory, planId }) => {
      const domains = builtinDomainResolver.listDomains().map((value) => structuredClone(value) as any)
      const overlays = builtinDomainResolver.listOverlays().map((value) => structuredClone(value) as any)
      const develop = domains.find((value) => value.id === "develop")!
      if (change === "domain-revision") develop.revision = "changed"
      if (change === "policy") develop.allowedOperations = develop.allowedOperations.filter((op: string) => op !== "delegate")
      if (change === "skill-reference") develop.skills = [{ name: "different-guide", revision: "1", description: "Different guidance" }]
      if (change === "overlay-revision") overlays[0].revision = "changed"
      const registry = new DomainRegistry({ defaultSelection: { domain: "develop", skills: [] }, domains, overlays })
      const executors = new DomainExecutionRegistry([generalExecutionModule, {
        ...developExecutionModule,
        proposal: { ...developExecutionModule.proposal, revision: change === "strategy" ? "changed" : "1" },
      }], change === "missing-overlay" ? [] : [hackathonExecutionOverlay])
      const adapter = runtime(), host = new KernelHost(adapter, { directory, domains: registry, domainExecutions: executors })
      expect((await host.readStatus("root", workspace)).planningState).toBe("plan_ready")
      await expect(host.control("root", { type: "planning.execute", planId })).rejects.toThrow("PLAN_DOMAIN_BINDING_CHANGED")
      expect(adapter.calls.opened).toBe(0)
      expect(adapter.calls.handoffs).toHaveLength(0)
      expect(adapter.calls.graphs).toHaveLength(0)
      expect((await new ReviewedPlanStore({ directory }).load({ planId })).plan.planId).toBe(planId)
      expect((await host.control("root", { type: "planning.discard" })).planningState).toBe("idle")
    })
  })
}

test("legacy plans remain inspectable and discardable but cannot execute without a reviewed domain recipe", async () => {
  await fixture(async ({ root, workspace, directory, planId }) => {
    const saved = await new ReviewedPlanStore({ directory }).load({ planId })
    const legacyDirectory = join(root, "legacy")
    await new ReviewedPlanStore({ directory: legacyDirectory }).save({ ...saved, domainBinding: undefined })
    const adapter = runtime(), host = new KernelHost(adapter, { directory: legacyDirectory })
    expect((await host.readStatus("root", workspace)).planningState).toBe("plan_ready")
    await expect(host.control("root", { type: "planning.execute", planId })).rejects.toThrow("PLAN_DOMAIN_BINDING_REQUIRED")
    expect(adapter.calls.handoffs).toHaveLength(0)
    expect((await new ReviewedPlanStore({ directory: legacyDirectory }).load({ planId })).plan.planId).toBe(planId)
    await host.control("root", { type: "planning.discard" })
    expect(host.status("root").planningState).toBe("idle")
  })
})

test("an execution strategy cannot rewrite reviewed instructions on explicit execute", async () => {
  let rewrite = false
  const executors = new DomainExecutionRegistry([generalExecutionModule, developExecutionModule], [{
    ...hackathonExecutionOverlay,
    proposal: {
      ...hackathonExecutionOverlay.proposal,
      apply(input) {
        const result = hackathonExecutionOverlay.proposal.apply(input)
        if (rewrite && result.kind === "work_graph") result.graph.units[0]!.instructions = "Unreviewed replacement"
        return result
      },
    },
  }])
  await fixture(async ({ host, adapter, directory, planId }) => {
    rewrite = true
    await expect(host.control("root", { type: "planning.execute", planId })).rejects.toThrow("PLAN_EXECUTION_GRAPH_CHANGED")
    expect(adapter.calls.handoffs).toHaveLength(0)
    expect(adapter.calls.graphs).toHaveLength(0)
    expect((await new ReviewedPlanStore({ directory }).load({ planId })).plan.planId).toBe(planId)
    rewrite = false
    await host.control("root", { type: "planning.execute", planId })
    expect(adapter.calls.handoffs).toHaveLength(1)
    expect(adapter.calls.graphs[0].units[0].instructions).toBe("Approved instructions")
  }, executors)
})
