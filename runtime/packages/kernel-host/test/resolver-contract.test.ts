import { contractFixture } from "./contract-fixture"
import { afterEach, expect, test } from "bun:test"
import { mkdtemp, mkdir, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { DomainExecutionRegistry, DomainRegistry, builtinDomainResolver } from "@base-harness/domain"
import type {
  DomainExecutionModule,
  DomainExecutionProposal,
  DomainManifest,
  DomainPreparation,
  DomainResolver,
  OverlayManifest,
} from "@base-harness/domain-contracts"
import { KernelHost } from "../src"
import { ReviewedPlanStore } from "../src/reviewed-plan-store"

const roots: string[] = []
afterEach(async () => { for (const root of roots.splice(0)) await rm(root, { recursive: true, force: true }) })

function customRegistry() {
  const domain: DomainManifest = {
    schemaVersion: "domain-spec-v1", id: "fixture-research", revision: "fixture-r1", description: "Read-only fixture domain",
    allowedOperations: ["read", "search", "question", "control"], allowedSubagentTypes: [],
    planning: { requiresPlan: false }, verification: { defaultStrength: "structural", criterionTemplates: ["fixture-observation"] },
    measurement: { summarySchemaVersion: "evidence-summary-v1", requiredFields: ["observed"] },
    compatibleOverlays: ["first", "second"], skills: [],
  }
  const overlays: OverlayManifest[] = ["first", "second"].map((id) => ({
    schemaVersion: "overlay-spec-v1", id, revision: id + "-1", description: "Fixture modifier",
    defaultDomain: domain.id, compatibleDomains: [domain.id],
    planning: { requiresPlan: false, demoFirst: false }, skills: [],
  }))
  return new DomainRegistry({ defaultSelection: { domain: domain.id, skills: [] }, domains: [domain], overlays })
}

const fixtureExecutionModule: DomainExecutionModule = {
  id: "fixture-research-execution",
  revision: "fixture-r1",
  domainId: "fixture-research",
  preparation: {
    id: "fixture-research-context",
    revision: "fixture-r1",
    prepare(input): DomainPreparation {
      return {
        schemaVersion: "domain-preparation-v1",
        domainId: "fixture-research",
        mode: "read",
        goal: input.goal,
        workspace: input.workspace,
        instructions: ["Inspect without changing workspace files."],
        allowedOperations: [...input.policy.allowedOperations] as DomainPreparation["allowedOperations"],
        allowedSubagentTypes: [...input.policy.allowedSubagentTypes],
        overlays: [],
        environment: { ...input.environment },
      }
    },
  },
  proposal: {
    id: "fixture-research-proposal",
    revision: "fixture-r1",
    normalize(input) {
      return structuredClone(input.proposal) as DomainExecutionProposal
    },
  },
}

function runtime() {
  let current: any = { sessionID: "s", runId: "", phase: "inactive" }
  const calls = { open: [] as any[], contracts: [] as any[], graphs: [] as any[] }
  return {
    calls,
    openRun: async (input: any) => {
      calls.open.push(input)
      return current = { ...current, runId: "fixture-run", phase: "planning", workspace: input.workspace }
    },
    proposeContract: async (_id: string, proposal: any) => {
      calls.contracts.push(proposal)
      return current = { ...current, contractStatus: "accepted" }
    },
    acceptWorkGraph: async (_id: string, graph: any) => { calls.graphs.push(graph); return current },
    beginDirect: () => { current = { ...current, phase: "direct" } },
    beginPlanning: () => {},
    status: () => current,
  }
}

async function fixture(domains: DomainResolver = customRegistry()) {
  const directory = await mkdtemp(join(tmpdir(), "harness-resolver-"))
  roots.push(directory)
  const workspace = join(directory, "workspace")
  await mkdir(workspace)
  const options = {
    domains,
    ...(domains === builtinDomainResolver ? {} : {
      domainExecutions: new DomainExecutionRegistry([fixtureExecutionModule]),
    }),
    directory: join(directory, "plans"),
    sessionState: { directory: join(directory, "sessions") },
  }
  const execution = runtime()
  const host = new KernelHost(execution, options)
  host.registerMetaReviewer(async (request) => ({ phase: request.phase, outcome: "pass", issues: [] }))
  return { host, execution, options, workspace }
}

function contract() {
  return contractFixture({
    interpretation: { version: 1, candidates: [] },
    claims: [{ claimId: "claim", criterionIds: ["criterion"], applicability: { status: "resolved" }, scope: { targets: ["input"] } }],
    criteria: [{ criterionId: "criterion", claimIds: ["claim"], risk: "low" }],
  })
}

test("a domain absent from Kernel literals drives the existing Host policy and contract path", async () => {
  const f = await fixture()
  expect(f.host.status("s").domain).toBe("fixture-research")
  await f.host.control("s", { type: "domain.set", domain: "fixture-research" }, undefined, f.workspace)
  await f.host.openRun({ sessionID: "s", workspace: f.workspace, goal: "inspect" })
  const accepted = await f.host.proposeContract("s", contract())
  expect(accepted.planningDecision).toBe("direct")
  expect(f.execution.calls.open[0].domainPolicy.domainId).toBe("fixture-research")
  expect(f.execution.calls.open[0].domainPolicy.domainRevision).toBe("fixture-r1")
  expect(f.execution.calls.contracts[0].criteria[0].verificationTemplate).toBe("fixture-observation")
  expect(() => f.host.assertToolAllowed("s", "read")).not.toThrow()
  expect(() => f.host.assertToolAllowed("s", "write")).toThrow("DOMAIN_PERMISSION_DENIED")
  expect(() => f.host.assertToolAllowed("s", "unclassified")).toThrow("DOMAIN_PERMISSION_UNKNOWN")
})

test("Host presentation cannot mutate the registry or change the next permission decision", async () => {
  const f = await fixture()
  const selected = { domain: "fixture-research", skills: [] }
  const cached = f.options.domains.resolve(selected)
  const status = f.host.status("s")
  status.domainPolicy.allowedOperations.push("mutate")
  status.domainPolicy.verification.criterionTemplates.length = 0
  expect(f.options.domains.resolve(selected)).toBe(cached)
  expect(f.host.status("s").domainPolicy.allowedOperations).not.toContain("mutate")
  expect(f.host.status("s").domainPolicy.verification.criterionTemplates).toEqual(["fixture-observation"])
  expect(() => f.host.assertToolAllowed("s", "write")).toThrow("DOMAIN_PERMISSION_DENIED")
})

test("unknown selections are rejected before execution and do not poison the current selection", async () => {
  const f = await fixture()
  await expect(f.host.control("s", { type: "domain.set", domain: "not-registered" }, undefined, f.workspace)).rejects.toThrow("DOMAIN_UNKNOWN")
  await expect(f.host.control("s", { type: "skill.set", skill: "not-registered", enabled: true }, undefined, f.workspace)).rejects.toThrow("OVERLAY_UNKNOWN")
  await expect(f.host.openRun({ sessionID: "s", workspace: f.workspace, goal: "inspect", defaultDomain: "not-registered" })).rejects.toThrow("DOMAIN_UNKNOWN")
  expect(f.execution.calls.open).toHaveLength(0)
  expect(f.host.status("s").domain).toBe("fixture-research")
  await f.host.openRun({ sessionID: "s", workspace: f.workspace, goal: "inspect" })
  expect(f.execution.calls.open).toHaveLength(1)
})

test("metadata overlays without an explicitly registered execution overlay fail before a run opens", async () => {
  const f = await fixture()
  await f.host.control("s", { type: "skill.set", skill: "first", enabled: true }, undefined, f.workspace)
  await expect(f.host.openRun({ sessionID: "s", workspace: f.workspace, goal: "inspect" }))
    .rejects.toThrow("DOMAIN_EXECUTION_OVERLAY_UNREGISTERED")
  expect(f.execution.calls.open).toHaveLength(0)
})

test("injected selection validation supports multiple modifiers without changing the signed session format", async () => {
  const f = await fixture()
  for (const skill of ["first", "second"]) await f.host.control("s", { type: "skill.set", skill, enabled: true }, undefined, f.workspace)
  const coldExecution = runtime(), cold = new KernelHost(coldExecution, f.options)
  const loaded = await cold.readStatus("s", f.workspace)
  expect(loaded.domain).toBe("fixture-research")
  expect(loaded.skills).toEqual(["first", "second"])
  expect(loaded.domainPolicy.skillRevisions).toEqual(["first-1", "second-1"])
  expect(coldExecution.calls.open).toHaveLength(0)
  const withoutRegistration = new KernelHost(runtime(), { ...f.options, domains: builtinDomainResolver })
  await expect(withoutRegistration.readStatus("s", f.workspace)).rejects.toThrow("SESSION_INTEGRITY_INVALID")
})

test("invalid selection controls cannot consume a valid previously reviewed plan", async () => {
  const f = await fixture(builtinDomainResolver)
  await f.host.control("s", { type: "planning.plan_once" }, undefined, f.workspace)
  await f.host.openRun({ sessionID: "s", workspace: f.workspace, goal: "one change" })
  await f.host.proposeContract("s", contract())
  const planned = await f.host.acceptWorkGraph("s", { units: [{
    id: "unit", title: "one change", claimIds: ["claim"], criterionIds: ["criterion"],
    dependsOn: [], readSet: [], writeSet: ["artifact.txt"],
  }] })
  expect(planned.planningState).toBe("plan_ready")
  await expect(f.host.control("s", { type: "domain.set", domain: "missing" })).rejects.toThrow("DOMAIN_UNKNOWN")
  const saved = await new ReviewedPlanStore(f.options).load({ sessionID: "s" })
  expect(saved.plan.planId).toBe(planned.activePlanId)
  expect(f.host.status("s").planningState).toBe("plan_ready")
  expect(f.execution.calls.graphs).toHaveLength(0)
})
