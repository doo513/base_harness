import { expect, test } from "bun:test"
import type {
  ContractBody,
  DomainExecutionModule,
  DomainExecutionOverlayModule,
  DomainExecutionProposal,
  DomainPreparationInput,
  DomainProposalInput,
} from "@base-harness/domain-contracts"
import {
  builtinDomainExecutionRegistry,
  developExecutionModule,
  DomainExecutionRegistry,
  generalExecutionModule,
  hackathonExecutionOverlay,
} from "../src"

const policy = (domainId: "general" | "develop") => ({
  domainId,
  domainRevision: domainId + "-1",
  skillRevisions: [],
  allowedOperations: domainId === "general" ? ["read", "search"] : ["read", "mutate", "execute"],
  allowedSubagentTypes: domainId === "general" ? ["explore"] : ["build"],
  requiresPlan: false,
  demoFirst: false,
  verification: { defaultStrength: "structural" as const, criterionTemplates: ["artifact"] },
  measurement: { summarySchemaVersion: "evidence-summary-v1", requiredFields: ["observed"] },
})

const contract: ContractBody = {
  goal: "Inspect or change artifact.txt",
  criteria: [{ criterionId: "criterion", statement: "Artifact is correct", claimIds: ["claim"], required: true, risk: "low" }],
  claims: [{
    claimId: "claim", criterionIds: ["criterion"], statement: "Artifact is correct", origin: "user",
    kind: "artifact", scope: { targets: ["artifact.txt"], capabilities: ["read"], exclusions: [] },
    applicability: {}, predicate: { type: "exists" },
    verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
  }],
  constraints: [],
}

function prepared(module: DomainExecutionModule) {
  const domainId = module.domainId as "general" | "develop"
  return module.preparation.prepare({
    sessionID: "session", workspace: "/workspace", goal: contract.goal,
    selection: { domain: domainId, skills: [] }, policy: policy(domainId), skills: [],
    executor: { id: "fixture", revision: "1", kind: "model_api", modelId: "model", options: {} },
    environment: { platform: "test" },
  } as DomainPreparationInput)
}

function proposal(module: DomainExecutionModule, value: unknown): DomainProposalInput {
  const domainId = module.domainId as "general" | "develop"
  return {
    sessionID: "session", runId: "run-1", proposal: value, preparation: prepared(module), contract,
    binding: {
      schemaVersion: "domain-execution-binding-v1", runId: "run-1",
      selection: { domain: domainId, skills: [] }, policy: policy(domainId),
      module: { id: module.id, revision: module.revision },
      preparationStrategy: { id: module.preparation.id, revision: module.preparation.revision },
      proposalStrategy: { id: module.proposal.id, revision: module.proposal.revision },
      overlays: [],
      executor: { id: "fixture", revision: "1", kind: "model_api", modelId: "model", options: {} },
    },
  }
}

test("General prepares read-only context and accepts a result path without a WorkGraph", () => {
  const context = prepared(generalExecutionModule)
  expect(context).toMatchObject({ domainId: "general", mode: "read", allowedOperations: ["read", "search"] })
  expect(generalExecutionModule.proposal.normalize(proposal(generalExecutionModule, {
    kind: "direct", dispatch: "adapter", instruction: "Read artifact.txt",
  }))).toEqual({ kind: "direct", dispatch: "adapter", instruction: "Read artifact.txt", mutationPolicy: "forbid" })
  expect(() => generalExecutionModule.proposal.normalize(proposal(generalExecutionModule, {
    kind: "work_graph", graph: { units: [], integrationPaths: [] },
  }))).toThrow("DOMAIN_PROPOSAL_FORBIDDEN")
  expect(() => generalExecutionModule.proposal.normalize(proposal(generalExecutionModule, {
    kind: "direct", instruction: "Change it", mutationPolicy: "capture",
  }))).toThrow("DOMAIN_PROPOSAL_FORBIDDEN")
})

test("Develop normalizes a bound WorkGraph without retaining actor objects", () => {
  const raw = { kind: "work_graph", graph: { units: [{
    id: "unit", title: "Change", claimIds: ["claim"], criterionIds: ["criterion"],
    readSet: ["./artifact.txt"], writeSet: ["artifact.txt"], dependsOn: [],
  }] } }
  const result = developExecutionModule.proposal.normalize(proposal(developExecutionModule, raw))
  expect(result).toEqual({ kind: "work_graph", graph: { integrationPaths: [], units: [{
    id: "unit", title: "Change", instructions: "Change", claimIds: ["claim"], criterionIds: ["criterion"],
    dependsOn: [], readSet: ["artifact.txt"], writeSet: ["artifact.txt"], integrationRequests: [],
  }] } })
  raw.graph.units[0]!.writeSet[0] = "other.txt"
  expect(result.kind === "work_graph" && result.graph.units[0]!.writeSet).toEqual(["artifact.txt"])
  expect(() => developExecutionModule.proposal.normalize(proposal(developExecutionModule, {
    kind: "work_graph", graph: { units: [{ ...raw.graph.units[0], claimIds: ["unknown"] }] },
  }))).toThrow("DOMAIN_PROPOSAL_BINDING_INVALID")
})

test("Hackathon composes around Develop, requires a WorkGraph, and prioritizes a demo root", () => {
  const overlayPolicy = {
    ...policy("develop"),
    skillRevisions: ["hackathon-1"],
    requiresPlan: true,
    demoFirst: true,
  }
  const preparationInput: DomainPreparationInput = {
    sessionID: "session", workspace: "/workspace", goal: contract.goal,
    selection: { domain: "develop", skills: ["hackathon"] },
    policy: overlayPolicy,
    skills: [],
    executor: { id: "fixture", revision: "1", kind: "model_api", modelId: "model", options: {} },
    environment: { platform: "test" },
  }
  const preparation = hackathonExecutionOverlay.preparation.apply({
    ...preparationInput,
    overlayId: "hackathon",
    overlayRevision: "hackathon-1",
    preparation: developExecutionModule.preparation.prepare(preparationInput),
  })
  const binding = {
    schemaVersion: "domain-execution-binding-v1" as const,
    runId: "run-1",
    selection: { domain: "develop", skills: ["hackathon"] },
    policy: overlayPolicy,
    module: { id: developExecutionModule.id, revision: developExecutionModule.revision },
    preparationStrategy: {
      id: developExecutionModule.preparation.id,
      revision: developExecutionModule.preparation.revision,
    },
    proposalStrategy: { id: developExecutionModule.proposal.id, revision: developExecutionModule.proposal.revision },
    overlays: [{
      overlayId: "hackathon",
      overlayRevision: "hackathon-1",
      module: { id: hackathonExecutionOverlay.id, revision: hackathonExecutionOverlay.revision },
      preparationStrategy: {
        id: hackathonExecutionOverlay.preparation.id,
        revision: hackathonExecutionOverlay.preparation.revision,
      },
      proposalStrategy: {
        id: hackathonExecutionOverlay.proposal.id,
        revision: hackathonExecutionOverlay.proposal.revision,
      },
    }],
    executor: preparationInput.executor,
  }
  expect(preparation.overlays).toEqual([{ id: "hackathon", revision: "hackathon-1" }])
  expect(preparation.instructions.join("\n")).toContain("smallest demonstrable vertical slice")
  expect(() => hackathonExecutionOverlay.proposal.apply({
    sessionID: "session", runId: "run-1", overlayId: "hackathon", overlayRevision: "hackathon-1",
    proposal: { kind: "direct", dispatch: "attached", instruction: "Build", mutationPolicy: "capture" },
    preparation, binding, contract,
  })).toThrow("DOMAIN_PROPOSAL_FORBIDDEN")
  const normalized = developExecutionModule.proposal.normalize({
    sessionID: "session", runId: "run-1", preparation, binding, contract,
    proposal: { kind: "work_graph", graph: { units: [
      { id: "polish", title: "Polish", claimIds: ["claim"], criterionIds: ["criterion"],
        dependsOn: ["demo"], readSet: ["artifact.txt"], writeSet: ["artifact.txt"] },
      { id: "demo", title: "Demo", claimIds: ["claim"], criterionIds: ["criterion"],
        dependsOn: [], readSet: [], writeSet: ["demo.txt"] },
    ], integrationPaths: [] } },
  })
  const overlaid = hackathonExecutionOverlay.proposal.apply({
    sessionID: "session", runId: "run-1", overlayId: "hackathon", overlayRevision: "hackathon-1",
    proposal: normalized, preparation, binding, contract,
  })
  expect(overlaid.kind === "work_graph" && overlaid.graph.units.map((unit) => unit.id)).toEqual(["demo", "polish"])
})

test("execution modules are explicit, immutable registry choices and strategies are replaceable", () => {
  expect(builtinDomainExecutionRegistry.resolve("general")).toMatchObject({
    id: generalExecutionModule.id,
    revision: generalExecutionModule.revision,
    domainId: generalExecutionModule.domainId,
    preparation: { id: generalExecutionModule.preparation.id, revision: generalExecutionModule.preparation.revision },
    proposal: { id: generalExecutionModule.proposal.id, revision: generalExecutionModule.proposal.revision },
  })
  expect(builtinDomainExecutionRegistry.resolveOverlay("hackathon")).toMatchObject({
    id: hackathonExecutionOverlay.id,
    revision: hackathonExecutionOverlay.revision,
    overlayId: hackathonExecutionOverlay.overlayId,
    compatibleDomains: ["develop"],
  })
  expect(() => builtinDomainExecutionRegistry.resolve("unregistered")).toThrow("DOMAIN_EXECUTION_MODULE_UNREGISTERED")
  expect(() => builtinDomainExecutionRegistry.resolveOverlay("unregistered")).toThrow("DOMAIN_EXECUTION_OVERLAY_UNREGISTERED")
  expect(() => new DomainExecutionRegistry([generalExecutionModule, generalExecutionModule])).toThrow("DOMAIN_EXECUTION_MODULE_DUPLICATE")
  expect(() => new DomainExecutionRegistry([developExecutionModule], [
    hackathonExecutionOverlay, hackathonExecutionOverlay,
  ])).toThrow("DOMAIN_EXECUTION_OVERLAY_DUPLICATE")
  let calls = 0
  const replacement: DomainExecutionModule = {
    ...developExecutionModule,
    id: "fixture-module",
    proposal: { ...developExecutionModule.proposal, id: "fixture-proposal", normalize(input) {
      calls += 1
      return developExecutionModule.proposal.normalize(input)
    } },
  }
  const registry = new DomainExecutionRegistry([replacement])
  registry.resolve("develop").proposal.normalize(proposal(replacement, { kind: "direct", instruction: "Work" }))
  expect(calls).toBe(1)
})

test("registered strategy snapshots survive caller mutation and preserve the strategy receiver", () => {
  const direct = (instruction: string): DomainExecutionProposal => ({
    kind: "direct", dispatch: "attached", instruction, mutationPolicy: "capture",
  })
  const module = {
    ...developExecutionModule,
    preparation: {
      id: "original-preparation", revision: "1",
      prepare() { return { ...prepared(developExecutionModule), instructions: [this.id] } },
    },
    proposal: {
      id: "original-proposal", revision: "1",
      normalize() { return direct(this.id) },
    },
  } satisfies DomainExecutionModule
  const overlay = {
    id: "fixture-overlay", revision: "1", overlayId: "fixture", compatibleDomains: ["develop"],
    preparation: {
      id: "original-overlay-preparation", revision: "1",
      apply() { return { ...prepared(developExecutionModule), instructions: [this.id] } },
    },
    proposal: {
      id: "original-overlay-proposal", revision: "1",
      apply() { return direct(this.id) },
    },
  } satisfies DomainExecutionOverlayModule
  const registry = new DomainExecutionRegistry([module], [overlay])
  const pinnedModule = registry.resolve("develop")
  const pinnedOverlay = registry.resolveOverlay("fixture")
  const proposalInput = proposal(pinnedModule, direct("input"))

  module.id = "changed-module"
  module.preparation.id = "changed-preparation"
  module.preparation.prepare = () => { throw new Error("replacement preparation") }
  module.proposal.revision = "2"
  module.proposal.normalize = () => direct("replacement proposal")
  overlay.id = "changed-overlay"
  overlay.compatibleDomains.length = 0
  overlay.preparation.id = "changed-overlay-preparation"
  overlay.preparation.apply = () => { throw new Error("replacement overlay preparation") }
  overlay.proposal.id = "changed-overlay-proposal"
  overlay.proposal.apply = () => direct("replacement overlay proposal")

  expect(prepared(pinnedModule).instructions).toEqual(["original-preparation"])
  expect(pinnedModule.proposal.normalize(proposalInput)).toEqual(direct("original-proposal"))
  expect(pinnedModule.id).toBe(developExecutionModule.id)
  expect(pinnedModule.proposal.revision).toBe("1")
  expect(pinnedOverlay.compatibleDomains).toEqual(["develop"])
  const overlayInput = { overlayId: "fixture", overlayRevision: "fixture-1" }
  expect(pinnedOverlay.preparation.apply({
    ...overlayInput,
    sessionID: "session", workspace: "/workspace", goal: contract.goal,
    selection: proposalInput.binding.selection, policy: proposalInput.binding.policy,
    executor: proposalInput.binding.executor, skills: [], environment: {},
    preparation: proposalInput.preparation,
  }).instructions).toEqual(["original-overlay-preparation"])
  expect(pinnedOverlay.proposal.apply({
    ...proposalInput, ...overlayInput, proposal: direct("input"),
  })).toEqual(direct("original-overlay-proposal"))
  expect(pinnedOverlay.id).toBe("fixture-overlay")
  expect(Object.isFrozen(pinnedModule)).toBe(true)
  expect(Object.isFrozen(pinnedModule.preparation)).toBe(true)
  expect(Object.isFrozen(pinnedModule.proposal)).toBe(true)
  expect(Object.isFrozen(pinnedOverlay)).toBe(true)
  expect(Object.isFrozen(pinnedOverlay.preparation)).toBe(true)
  expect(Object.isFrozen(pinnedOverlay.proposal)).toBe(true)
  expect(Object.isFrozen(pinnedOverlay.compatibleDomains)).toBe(true)
  expect(Reflect.set(pinnedModule.proposal, "normalize", () => direct("late replacement"))).toBe(false)
  expect(Reflect.set(pinnedOverlay.proposal, "apply", () => direct("late replacement"))).toBe(false)
})

test("class strategies keep prototype entry points and private configuration for Domain and Overlay", () => {
  class Preparation {
    readonly id = "class-preparation"
    readonly revision = "1"
    readonly #instruction = "private preparation"
    prepare() { return { ...prepared(developExecutionModule), instructions: [this.#instruction] } }
  }
  class Proposal {
    readonly id = "class-proposal"
    readonly revision = "1"
    readonly #instruction = "private proposal"
    normalize(): DomainExecutionProposal { return { kind: "direct", dispatch: "attached", mutationPolicy: "capture", instruction: this.#instruction } }
  }
  class OverlayPreparation {
    readonly id = "class-overlay-preparation"
    readonly revision = "1"
    readonly #instruction = "private overlay preparation"
    apply() { return { ...prepared(developExecutionModule), instructions: [this.#instruction] } }
  }
  class OverlayProposal {
    readonly id = "class-overlay-proposal"
    readonly revision = "1"
    readonly #instruction = "private overlay proposal"
    apply(): DomainExecutionProposal { return { kind: "direct", dispatch: "attached", mutationPolicy: "capture", instruction: this.#instruction } }
  }
  const module = { ...developExecutionModule, preparation: new Preparation(), proposal: new Proposal() }
  const overlay = { ...hackathonExecutionOverlay, preparation: new OverlayPreparation(), proposal: new OverlayProposal() }
  const registry = new DomainExecutionRegistry([module], [overlay])
  module.preparation.prepare = () => { throw new Error("replaced") }
  module.proposal.normalize = () => { throw new Error("replaced") }
  overlay.preparation.apply = () => { throw new Error("replaced") }
  overlay.proposal.apply = () => { throw new Error("replaced") }
  const pinned = registry.resolve("develop"), pinnedOverlay = registry.resolveOverlay("hackathon")
  const input = proposal(pinned, { kind: "direct" })
  expect(prepared(pinned).instructions).toEqual(["private preparation"])
  expect(pinned.proposal.normalize(input)).toMatchObject({ instruction: "private proposal" })
  expect(pinnedOverlay.preparation.apply({
    sessionID: "session", workspace: "/workspace", goal: contract.goal, skills: [], environment: {},
    selection: input.binding.selection, policy: input.binding.policy, executor: input.binding.executor,
    overlayId: "hackathon", overlayRevision: "1", preparation: input.preparation,
  }).instructions).toEqual(["private overlay preparation"])
  expect(pinnedOverlay.proposal.apply({ ...input, overlayId: "hackathon", overlayRevision: "1",
    proposal: { kind: "direct", dispatch: "attached", instruction: "input", mutationPolicy: "capture" },
  })).toMatchObject({ instruction: "private overlay proposal" })
})

test("pinned class strategies fail closed when observable configuration drifts", () => {
  class Proposal {
    readonly id = "stateful-proposal"
    readonly revision = "1"
    instruction = "original"
    readonly options = { suffix: "result" }
    normalize(): DomainExecutionProposal {
      return {
        kind: "direct", dispatch: "attached", mutationPolicy: "capture",
        instruction: `${this.instruction} ${this.options.suffix}`,
      }
    }
  }
  const strategy = new Proposal()
  const registry = new DomainExecutionRegistry([{ ...developExecutionModule, proposal: strategy }])
  const pinned = registry.resolve("develop")
  expect(pinned.proposal.normalize(proposal(pinned, { kind: "direct" }))).toMatchObject({
    instruction: "original result",
  })

  strategy.options.suffix = "changed"
  expect(() => pinned.proposal.normalize(proposal(pinned, { kind: "direct" }))).toThrow(
    "DOMAIN_EXECUTION_MODULE_INVALID:strategy state changed after registration",
  )
})

test("pinned strategies fail closed when they mutate observable state during a call", () => {
  class Proposal {
    readonly id = "self-mutating-proposal"
    readonly revision = "1"
    calls = 0
    normalize(): DomainExecutionProposal {
      this.calls += 1
      return { kind: "direct", dispatch: "attached", mutationPolicy: "capture", instruction: "result" }
    }
  }
  const strategy = new Proposal()
  const registry = new DomainExecutionRegistry([{ ...developExecutionModule, proposal: strategy }])
  const pinned = registry.resolve("develop")
  expect(() => pinned.proposal.normalize(proposal(pinned, { kind: "direct" }))).toThrow(
    "DOMAIN_EXECUTION_MODULE_INVALID:strategy state changed after registration",
  )
})
