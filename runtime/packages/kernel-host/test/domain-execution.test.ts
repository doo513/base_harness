import { expect, test } from "bun:test"
import { mkdir, mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { DomainExecutionRegistry, builtinDomainResolver } from "@base-harness/domain"
import type { DomainExecutionModule, DomainExecutionProposal, DomainPreparation } from "@base-harness/domain-contracts"
import { KernelHost } from "../src"
import { contractFixture } from "./contract-fixture"

function moduleFixture(revision: string, calls: { prepare: number; normalize: number; goals: string[] }): DomainExecutionModule {
  return {
    id: "replaceable-develop-module",
    revision,
    domainId: "develop",
    preparation: {
      id: "replaceable-preparation",
      revision,
      prepare(input): DomainPreparation {
        calls.prepare += 1
        return {
          schemaVersion: "domain-preparation-v1",
          domainId: "develop",
          mode: "develop",
          goal: input.goal,
          workspace: input.workspace,
          instructions: ["custom preparation " + revision],
          allowedOperations: [...input.policy.allowedOperations] as DomainPreparation["allowedOperations"],
          allowedSubagentTypes: [...input.policy.allowedSubagentTypes],
          overlays: [],
          environment: { ...input.environment },
        }
      },
    },
    proposal: {
      id: "replaceable-proposal",
      revision,
      normalize(input): DomainExecutionProposal {
        calls.normalize += 1
        calls.goals.push(input.contract.goal)
        return {
          kind: "direct",
          dispatch: "adapter",
          instruction: `normalized-${revision}:${input.contract.goal}`,
          mutationPolicy: "forbid",
        }
      },
    },
  }
}

function runtimeFixture(accept = true) {
  let current: any = { sessionID: "domain-host", runId: "", phase: "inactive", contractStatus: "missing" }
  let sequence = 0
  const calls = { opened: [] as any[], contracts: 0, proposals: [] as any[], direct: 0 }
  return {
    calls,
    runtime: {
      openRun: async (input: any) => {
        calls.opened.push(input)
        current = { ...current, sessionID: input.sessionID, runId: `domain-run-${++sequence}`, phase: "planning", contractStatus: "missing" }
        return current
      },
      proposeContract: async () => {
        calls.contracts += 1
        current = { ...current, contractStatus: accept ? "accepted" : "missing" }
        return current
      },
      acceptWorkGraph: async () => current,
      submitDomainProposal: async (input: any) => {
        calls.proposals.push(structuredClone(input))
        return current
      },
      beginDirect: () => { calls.direct += 1; current = { ...current, phase: "direct" } },
      beginPlanning: () => { current = { ...current, phase: "planning" } },
      status: () => current,
    },
  }
}

function contract(uncertain = false) {
  return contractFixture({
    goal: "Inspect and report",
    criteria: [{ criterionId: "criterion", claimIds: ["claim"], risk: "low" }],
    claims: [{ claimId: "claim", criterionIds: ["criterion"], applicability: { status: "resolved" } }],
    interpretation: {
      version: 1,
      candidates: uncertain ? [{
        id: "format",
        kind: "missing_decision",
        impact: "user_preference",
        affectedClaimIds: ["claim"],
        affectedCriterionIds: ["criterion"],
        sourceRefs: [{ source: "request" }],
        statement: "Choose the report format",
      }] : [],
    },
  })
}

test("Host pins replaceable strategies and rechecks a staged proposal only after contract acceptance", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-host-"))
  const calls = { prepare: 0, normalize: 0, goals: [] as string[] }
  const module = moduleFixture("custom-7", calls)
  const fixture = runtimeFixture()
  const host = new KernelHost(fixture.runtime, {
    domains: builtinDomainResolver,
    domainExecutions: new DomainExecutionRegistry([module]),
    directory: join(workspace, ".plans"),
  })
  try {
    const opened = await host.openRun({
      sessionID: "domain-host",
      workspace,
      goal: "Inspect and report",
      defaultDomain: "develop",
      domainExecutor: { id: "fixture-adapter", revision: "adapter-r1", kind: "agent_runtime", modelId: "fixture", options: {} },
    })
    expect(opened.domainBinding).toMatchObject({
      runId: "domain-run-1",
      module: { id: module.id, revision: "custom-7" },
      preparationStrategy: { revision: "custom-7" },
      proposalStrategy: { revision: "custom-7" },
      executor: { id: "fixture-adapter", revision: "adapter-r1" },
    })
    expect(opened.domainPreparation.instructions).toEqual(["custom preparation custom-7"])
    expect(calls.prepare).toBe(1)
    await host.stageExecutionProposal("domain-host", { arbitrary: "adapter candidate" }, { source: "fixture" })
    const waiting = await host.proposeContract("domain-host", contract(true))
    expect(waiting.contractProcessing.outcome).toBe("needs_input")
    expect(waiting.planningState).toBe("awaiting_input")
    expect(fixture.calls.contracts).toBe(0)
    expect(fixture.calls.proposals).toHaveLength(0)
    expect(calls.normalize).toBe(0)

    const accepted = await host.proposeContract("domain-host", contract(false))
    expect(accepted.contractStatus).toBe("accepted")
    expect(fixture.calls.contracts).toBe(1)
    expect(fixture.calls.proposals).toHaveLength(1)
    expect(fixture.calls.proposals[0]).toMatchObject({
      runId: "domain-run-1",
      proposal: { kind: "direct", dispatch: "adapter", instruction: "normalized-custom-7:Inspect and report" },
    })
    expect(calls.normalize).toBe(1)
    expect(calls.goals).toEqual(["Inspect and report"])
  } finally {
    await rm(workspace, { recursive: true, force: true })
  }
})

test("rejected contracts and plan-only direct proposals never dispatch", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-gates-"))
  try {
    for (const planOnly of [false, true]) {
      const calls = { prepare: 0, normalize: 0, goals: [] as string[] }
      const fixture = runtimeFixture(planOnly)
      const host = new KernelHost(fixture.runtime, {
        domainExecutions: new DomainExecutionRegistry([moduleFixture(planOnly ? "plan" : "reject", calls)]),
        directory: join(workspace, planOnly ? ".plans-plan" : ".plans-reject"),
      })
      if (planOnly) await host.control("domain-host", { type: "planning.plan_once" })
      await host.openRun({ sessionID: "domain-host", workspace, goal: "Inspect and report" })
      await host.stageExecutionProposal("domain-host", { raw: true })
      const result = await host.proposeContract("domain-host", contract(false))
      expect(fixture.calls.proposals).toHaveLength(0)
      expect(calls.normalize).toBe(0)
      if (planOnly) expect(result.planningState).toBe("planning_decision")
      else expect(result.contractStatus).toBe("missing")
    }
  } finally {
    await rm(workspace, { recursive: true, force: true })
  }
})

test("a custom resolver cannot replace an open Run's callback using the same strategy identity", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-pinning-"))
  const calls = { prepare: 0, normalize: 0, goals: [] as string[] }
  const module = moduleFixture("pinned", calls)
  const fixture = runtimeFixture()
  const host = new KernelHost(fixture.runtime, {
    directory: join(workspace, ".plans"),
    domainExecutions: {
      resolve: () => module,
      resolveOverlay: () => { throw new Error("No overlays registered") },
    },
  })
  try {
    await host.openRun({ sessionID: "domain-host", workspace, goal: "Inspect and report" })
    module.proposal.normalize = () => { throw new Error("Replaced callback ran") }
    await host.stageExecutionProposal("domain-host", { raw: true })
    await host.proposeContract("domain-host", contract(false))
    expect(calls.normalize).toBe(1)
    expect(fixture.calls.proposals[0].proposal.instruction).toBe("normalized-pinned:Inspect and report")
  } finally {
    await rm(workspace, { recursive: true, force: true })
  }
})

test("Host supports class strategies from a custom resolver without losing their receiver", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-class-strategy-"))
  const base = moduleFixture("class", { prepare: 0, normalize: 0, goals: [] })
  class Preparation {
    readonly id = "class-preparation"
    readonly revision = "1"
    readonly #base = base.preparation
    prepare(input: Parameters<DomainExecutionModule["preparation"]["prepare"]>[0]) {
      return this.#base.prepare(input)
    }
  }
  class Proposal {
    readonly id = "class-proposal"
    readonly revision = "1"
    readonly #instruction = "Private class result"
    normalize(): DomainExecutionProposal {
      return { kind: "direct", dispatch: "adapter", mutationPolicy: "forbid", instruction: this.#instruction }
    }
  }
  const module = { ...base, preparation: new Preparation(), proposal: new Proposal() }
  const fixture = runtimeFixture()
  const host = new KernelHost(fixture.runtime, {
    directory: join(workspace, ".plans"),
    domainExecutions: { resolve: () => module, resolveOverlay: () => { throw new Error("No overlay") } },
  })
  try {
    await host.openRun({ sessionID: "domain-host", workspace, goal: "Inspect and report" })
    module.proposal.normalize = () => { throw new Error("Replaced callback") }
    await host.stageExecutionProposal("domain-host", { raw: true })
    await host.proposeContract("domain-host", contract(false))
    expect(fixture.calls.proposals[0].proposal.instruction).toBe("Private class result")
  } finally { await rm(workspace, { recursive: true, force: true }) }
})

test("Hackathon pins its overlay, rechecks a WorkGraph, and leaves execution behind the reviewed-plan gate", async () => {
  const root = await mkdtemp(join(tmpdir(), "base-harness-hackathon-host-"))
  const workspace = join(root, "workspace")
  await mkdir(workspace)
  const fixture = runtimeFixture()
  const host = new KernelHost(fixture.runtime, { directory: join(root, "plans") })
  let reviewedPlan: any
  host.registerMetaReviewer(async (request) => {
    if (request.phase === "plan") reviewedPlan = structuredClone(request.artifact)
    return { phase: request.phase, outcome: "pass", issues: [] }
  })
  try {
    await host.control("domain-host", { type: "skill.set", skill: "hackathon", enabled: true }, undefined, workspace)
    await host.control("domain-host", { type: "planning.plan_once" }, undefined, workspace)
    const opened = await host.openRun({
      sessionID: "domain-host",
      workspace,
      goal: "Inspect and report",
      defaultDomain: "develop",
    })
    expect(opened.domainBinding).toMatchObject({
      selection: { domain: "develop", skills: ["hackathon"] },
      policy: { skillRevisions: ["hackathon-1"], requiresPlan: true, demoFirst: true },
      overlays: [{
        overlayId: "hackathon",
        overlayRevision: "hackathon-1",
        module: { id: "hackathon-overlay-default", revision: "1" },
        preparationStrategy: { id: "hackathon-context", revision: "1" },
        proposalStrategy: { id: "hackathon-demo-first", revision: "1" },
      }],
    })
    expect(opened.domainPreparation.overlays).toEqual([{ id: "hackathon", revision: "hackathon-1" }])
    expect(opened.domainPreparation.instructions).toContain(
      "Use a reviewed WorkGraph; the Hackathon overlay does not authorize direct execution.",
    )

    await host.stageExecutionProposal("domain-host", {
      kind: "work_graph",
      graph: {
        units: [{
          id: "polish",
          title: "Polish result",
          instructions: "Polish the demonstrable result",
          claimIds: ["claim"],
          criterionIds: ["criterion"],
          dependsOn: ["demo"],
          readSet: ["demo.txt"],
          writeSet: ["result.txt"],
          integrationRequests: [],
        }, {
          id: "demo",
          title: "Build demo",
          instructions: "Build the smallest vertical slice",
          claimIds: ["claim"],
          criterionIds: ["criterion"],
          dependsOn: [],
          readSet: [],
          writeSet: ["demo.txt"],
          integrationRequests: [],
        }],
        integrationPaths: [],
      },
    })
    const planned = await host.proposeContract("domain-host", contract(false))
    expect(planned.planningState).toBe("plan_ready")
    expect(fixture.calls.proposals).toHaveLength(0)
    expect(reviewedPlan.steps.map((step: any) => [step.id, step.priority])).toEqual([
      ["demo", "demo_required"],
      ["polish", "required"],
    ])
    expect(reviewedPlan.workGraph.units.map((unit: any) => unit.id)).toEqual(["demo", "polish"])
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
