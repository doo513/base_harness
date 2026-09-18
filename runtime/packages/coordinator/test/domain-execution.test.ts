import { expect, test } from "bun:test"
import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import type {
  DomainExecutionBinding,
  DomainPreparation,
} from "../src"
import { CoordinatorRuntime } from "../src"
import type { ProcessVerificationClient, VerificationStatus } from "@base-harness/verification"

function verifierFactory() {
  return async (input: any) => {
    let status = {
      state: "open",
      runId: input.runId,
      scopeId: input.scopeId,
      rootScopeId: input.scopeId,
      goal: input.goalSources[0]?.text ?? "",
      contractStatus: "missing",
      criterionResults: [],
      claimResults: [],
      evidenceFamilies: [],
      evidenceRefs: [],
      candidateRefs: [],
      maxSameFailureRepairs: 2,
      readyEligible: false,
    } as VerificationStatus
    return {
      snapshot: () => status,
      subscribe: () => () => {},
      proposeContract: async (contract: VerificationStatus["goalContract"]) => (
        status = { ...status, contractStatus: "accepted", goalContract: contract }
      ),
      dispose: async () => {},
      close: async () => status,
    } as unknown as ProcessVerificationClient
  }
}

function binding(executorId: string): DomainExecutionBinding {
  return {
    schemaVersion: "domain-execution-binding-v1",
    selection: { domain: "general", skills: [] },
    policy: {
      domainId: "general",
      domainRevision: "general-test",
      skillRevisions: [],
      allowedOperations: ["read", "search"],
      allowedSubagentTypes: [],
      requiresPlan: false,
      demoFirst: false,
      verification: { defaultStrength: "structural", criterionTemplates: ["observation"] },
      measurement: { summarySchemaVersion: "evidence-summary-v1", requiredFields: ["observed"] },
    },
    module: { id: "general-test", revision: "1" },
    preparationStrategy: { id: "general-preparation-test", revision: "1" },
    proposalStrategy: { id: "general-proposal-test", revision: "1" },
    overlays: [],
    executor: { id: executorId, revision: "capability-1", kind: "agent_runtime", modelId: "fixture", options: {} },
  }
}

function preparation(workspace: string): DomainPreparation {
  return {
    schemaVersion: "domain-preparation-v1",
    domainId: "general",
    mode: "read",
    goal: "Inspect source.txt",
    workspace,
    instructions: ["Read only"],
    allowedOperations: ["read", "search"],
    allowedSubagentTypes: [],
    overlays: [],
    environment: {},
  }
}

const contract = {
  goal: "Inspect source.txt",
  criteria: [{ criterionId: "criterion", statement: "Return the observation", claimIds: ["claim"], required: true, risk: "low" as const }],
  claims: [{
    claimId: "claim",
    criterionIds: ["criterion"],
    origin: "user" as const,
    statement: "Return the observation",
    kind: "external" as const,
    scope: { targets: ["source.txt"], capabilities: ["read"], exclusions: [] },
    predicate: { type: "output_contains", value: "fixture" },
    verifierPolicy: { minimumStrength: "structural" as const, allowedVerifierIds: ["output"], minIndependentFamilies: 1 },
  }],
}

async function openAccepted(runtime: CoordinatorRuntime, sessionID: string, workspace: string, executorId: string) {
  const opened = await runtime.openRun({
    sessionID,
    workspace,
    goal: contract.goal,
    trigger: "manual",
    domainBinding: binding(executorId),
    domainPreparation: preparation(workspace),
  })
  await runtime.proposeContract(sessionID, contract)
  return opened
}

test("overlay strategy identities and preparation markers must match the run binding exactly", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-overlay-binding-"))
  const runtime = new CoordinatorRuntime(verifierFactory())
  try {
    const invalid = binding("adapter")
    invalid.selection.skills = ["fixture-overlay"]
    invalid.policy.skillRevisions = ["fixture-overlay-r1"]
    invalid.overlays = [{
      overlayId: "fixture-overlay",
      overlayRevision: "different-revision",
      module: { id: "fixture-overlay-module", revision: "1" },
      preparationStrategy: { id: "fixture-overlay-preparation", revision: "1" },
      proposalStrategy: { id: "fixture-overlay-proposal", revision: "1" },
    }]
    await expect(runtime.openRun({
      sessionID: "invalid-overlay-binding",
      workspace,
      goal: contract.goal,
      domainBinding: invalid,
      domainPreparation: preparation(workspace),
    })).rejects.toThrow("DOMAIN_RUN_BINDING_INVALID")

    const valid = structuredClone(invalid)
    valid.overlays[0]!.overlayRevision = "fixture-overlay-r1"
    await expect(runtime.openRun({
      sessionID: "invalid-overlay-preparation",
      workspace,
      goal: contract.goal,
      domainBinding: valid,
      domainPreparation: preparation(workspace),
    })).rejects.toThrow("DOMAIN_PREPARATION_INVALID")
    expect(runtime.status("invalid-overlay-binding").phase).toBe("inactive")
    expect(runtime.status("invalid-overlay-preparation").phase).toBe("inactive")
  } finally {
    runtime.resetForTest()
    await rm(workspace, { recursive: true, force: true })
  }
})

test("one fixed Domain dispatcher uses each run binding and only records candidate output", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-dispatch-"))
  const runtime = new CoordinatorRuntime(verifierFactory())
  const seen: Array<{ sessionID: string; runId: string; executorId: string }> = []
  const dispatcher = async (request: any) => {
    seen.push({ sessionID: request.sessionID, runId: request.runId, executorId: request.binding.executor.id })
    return {
      runId: request.runId,
      output: "fixture:" + request.binding.executor.id,
      changedFiles: [],
      adapterId: request.binding.executor.id,
      modelId: request.binding.executor.modelId,
    }
  }
  runtime.registerDomainExecutor(dispatcher)
  expect(() => runtime.registerDomainExecutor(async () => ({
    runId: "other", output: "", changedFiles: [], adapterId: "other",
  }))).toThrow("DOMAIN_EXECUTOR_ALREADY_REGISTERED")
  try {
    for (const [sessionID, executorId] of [["domain-a", "adapter-a"], ["domain-b", "adapter-b"]] as const) {
      const opened = await openAccepted(runtime, sessionID, workspace, executorId)
      const status = await runtime.submitDomainProposal({
        sessionID,
        runId: opened.runId,
        proposal: { kind: "direct", dispatch: "adapter", instruction: contract.goal, mutationPolicy: "forbid" },
        context: {},
      })
      expect(status.domainResult).toMatchObject({ runId: opened.runId, output: "fixture:" + executorId, adapterId: executorId })
      expect(status.evidenceCount).toBe(0)
      expect(status.candidateCount).toBe(0)
      expect(status.readyEligible).toBe(false)
    }
    expect(seen.map((item) => [item.sessionID, item.executorId])).toEqual([
      ["domain-a", "adapter-a"],
      ["domain-b", "adapter-b"],
    ])
    expect(seen[0]!.runId).not.toBe(seen[1]!.runId)
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(workspace, { recursive: true, force: true })
  }
})

test("cancelled and replaced runs discard late Domain results", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-stale-"))
  const runtime = new CoordinatorRuntime(verifierFactory())
  let release!: () => void
  let entered!: () => void
  const gate = new Promise<void>((resolve) => { release = resolve })
  const started = new Promise<void>((resolve) => { entered = resolve })
  runtime.registerDomainExecutor(async (request) => {
    entered()
    await gate
    return { runId: request.runId, output: "late", changedFiles: [], adapterId: request.binding.executor.id }
  })
  try {
    const old = await openAccepted(runtime, "domain-stale", workspace, "old-adapter")
    const pending = runtime.submitDomainProposal({
      sessionID: "domain-stale",
      runId: old.runId,
      proposal: { kind: "direct", dispatch: "adapter", instruction: contract.goal, mutationPolicy: "forbid" },
      context: {},
    })
    await started
    await runtime.cancel("domain-stale")
    const fresh = await runtime.openRun({
      sessionID: "domain-stale",
      workspace,
      goal: contract.goal,
      trigger: "manual",
      domainBinding: binding("new-adapter"),
      domainPreparation: preparation(workspace),
    })
    release()
    await pending
    expect(fresh.runId).not.toBe(old.runId)
    expect(runtime.status("domain-stale").domainBinding?.executor.id).toBe("new-adapter")
    expect(runtime.status("domain-stale").domainResult).toBeUndefined()
    await runtime.recordDomainResult({
      sessionID: "domain-stale",
      runId: old.runId,
      result: { output: "also late", changedFiles: [], adapterId: "old-adapter" },
    })
    expect(runtime.status("domain-stale").domainResult).toBeUndefined()
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(workspace, { recursive: true, force: true })
  }
})

test("General result admission rejects empty, changed, or unpinned adapter output", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-result-admission-"))
  const runtime = new CoordinatorRuntime(verifierFactory())
  runtime.registerDomainExecutor(async (request) => {
    const common = {
      runId: request.runId,
      output: "fixture",
      changedFiles: [] as string[],
      adapterId: request.binding.executor.id,
      modelId: request.binding.executor.modelId,
    }
    if (request.sessionID === "empty") return { ...common, output: "   " }
    if (request.sessionID === "changed") return { ...common, changedFiles: ["source.txt"] }
    if (request.sessionID === "adapter") return { ...common, adapterId: "different-adapter" }
    return { ...common, modelId: "different-model" }
  })
  try {
    for (const [sessionID, code] of [
      ["empty", "DOMAIN_RESULT_EMPTY"],
      ["changed", "DOMAIN_RESULT_MUTATION_FORBIDDEN"],
      ["adapter", "DOMAIN_RESULT_EXECUTOR_MISMATCH"],
      ["model", "DOMAIN_RESULT_MODEL_MISMATCH"],
    ] as const) {
      const opened = await openAccepted(runtime, sessionID, workspace, sessionID + "-adapter")
      const status = await runtime.submitDomainProposal({
        sessionID,
        runId: opened.runId,
        proposal: { kind: "direct", dispatch: "adapter", instruction: contract.goal, mutationPolicy: "forbid" },
        context: {},
      })
      expect(status.outcome).toBe("blocked")
      expect(status.failureKind).toBe("model_protocol_error")
      expect(status.message).toContain(code)
      expect(status.domainResult).toBeUndefined()
    }
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(workspace, { recursive: true, force: true })
  }
})

test("General content_equals admission rejects a report that only contains the expected value", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-result-equals-"))
  const runtime = new CoordinatorRuntime(verifierFactory())
  try {
    const opened = await runtime.openRun({
      sessionID: "root", workspace, goal: contract.goal, trigger: "manual",
      domainBinding: binding("general-reader"),
      domainPreparation: preparation(workspace),
    })
    await runtime.proposeContract("root", {
      ...contract,
      claims: contract.claims.map((claim) => ({
        ...claim,
        predicate: { type: "content_equals", value: "expected report" },
      })),
    })
    runtime.registerDomainExecutor(async () => ({
      runId: opened.runId,
      output: "prefix expected report suffix",
      changedFiles: [],
      adapterId: "general-reader",
      modelId: "fixture",
    }))

    const status = await runtime.submitDomainProposal({
      sessionID: "root",
      runId: opened.runId,
      proposal: { kind: "direct", dispatch: "adapter", instruction: "report", mutationPolicy: "forbid" },
      context: {},
    })

    expect(status.outcome).toBe("blocked")
    expect(status.message).toContain("DOMAIN_RESULT_MISMATCH")
    expect(status.domainResult).toBeUndefined()
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(workspace, { recursive: true, force: true })
  }
})

test("an attached Run result is immutable after its first accepted value", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-result-conflict-"))
  const runtime = new CoordinatorRuntime(verifierFactory())
  try {
    const opened = await openAccepted(runtime, "attached-result", workspace, "session-model")
    await runtime.submitDomainProposal({
      sessionID: "attached-result",
      runId: opened.runId,
      proposal: { kind: "direct", dispatch: "attached", instruction: contract.goal, mutationPolicy: "forbid" },
      context: {},
    })
    const first = await runtime.recordDomainResult({
      sessionID: "attached-result",
      runId: opened.runId,
      result: { output: "fixture", changedFiles: [], adapterId: "session-model", modelId: "fixture" },
    })
    expect(first.domainResult?.output).toBe("fixture")

    const retry = await runtime.recordDomainResult({
      sessionID: "attached-result",
      runId: opened.runId,
      result: { output: "fixture", changedFiles: [], adapterId: "session-model", modelId: "fixture" },
    })
    expect(retry.outcome).toBeUndefined()
    expect(retry.domainResult?.output).toBe("fixture")

    const conflict = await runtime.recordDomainResult({
      sessionID: "attached-result",
      runId: opened.runId,
      result: { output: "replacement", changedFiles: [], adapterId: "session-model", modelId: "fixture" },
    })
    expect(conflict.outcome).toBe("blocked")
    expect(conflict.failureKind).toBe("model_protocol_error")
    expect(conflict.message).toContain("DOMAIN_RESULT_CONFLICT")
    expect(conflict.domainResult?.output).toBe("fixture")
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(workspace, { recursive: true, force: true })
  }
})
