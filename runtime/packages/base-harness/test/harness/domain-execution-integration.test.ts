import { expect, test } from "bun:test"
import { createHash } from "node:crypto"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { CoordinatorRuntime, RunRepository } from "@base-harness/coordinator"
import { builtinDomainExecutionRegistry, builtinDomainResolver } from "@base-harness/domain"
import { KernelHost } from "@base-harness/kernel-host"
import type { ExecutionBackend } from "../../src/harness/execution/backend"
import { ExecutionBackends } from "../../src/harness/execution/backend-router"
import { dispatchDomainExecution } from "../../src/harness/domain-execution"

const sha256 = (value: string) => createHash("sha256").update(value).digest("hex")

function contract(input: {
  goal: string
  target: string
  capability: string
  predicate: { type: string; value?: string }
}) {
  return {
    goal: input.goal,
    criteria: [{
      criterionId: "criterion",
      statement: "The requested result is observable",
      claimIds: ["claim"],
      required: true,
      risk: "low" as const,
    }],
    claims: [{
      claimId: "claim",
      criterionIds: ["criterion"],
      origin: "user" as const,
      statement: "The requested result is observable",
      kind: "artifact" as const,
      scope: { targets: [input.target], capabilities: [input.capability], exclusions: [] },
      applicability: {},
      predicate: input.predicate,
      verifierPolicy: {
        minimumStrength: "structural" as const,
        allowedVerifierIds: ["file"],
        minIndependentFamilies: 1,
      },
    }],
    constraints: [],
    interpretation: { version: 1 as const, candidates: [] },
  }
}

function runtimeFor(stateDirectory: string) {
  return new CoordinatorRuntime(undefined, {
    repository: new RunRepository<any>({ stateDirectory }),
  })
}

function hostFor(runtime: CoordinatorRuntime, planDirectory: string) {
  const host = new KernelHost(runtime, {
    domains: builtinDomainResolver,
    domainExecutions: builtinDomainExecutionRegistry,
    directory: planDirectory,
  })
  host.registerMetaReviewer(async (request) => ({ phase: request.phase, outcome: "pass", issues: [] }))
  runtime.registerCompletionGate((sessionID) => host.canVerifyRoot(sessionID))
  // The application Task adapter always installs the root continuation. These
  // integration tests use a no-op continuation because their graphs do not
  // request shared-file integration.
  runtime.registerIntegrationExecutor(async () => undefined)
  return host
}

test("the application Domain adapter runs a controlled process with the pinned run and read-only preparation", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-domain-adapter-"))
  const source = join(workspace, "source.txt")
  await writeFile(source, "controlled observation\n")
  const before = sha256(await readFile(source, "utf8"))
  const calls: Array<{ runId?: string; phase?: string; cwd: string }> = []
  const backend: ExecutionBackend = {
    id: "stage3-controlled-process",
    kind: "agent_runtime",
    async discover() {
      return {
        adapterID: this.id,
        backendId: this.id,
        kind: this.kind,
        revision: "fixture-r1",
        models: ["fixture-model"],
        reasoningEfforts: [],
      }
    },
    async execute(input) {
      calls.push({ runId: input.runId, phase: input.phase, cwd: input.workspace })
      const child = Bun.spawn([
        process.execPath,
        "-e",
        "const value = await Bun.file('source.txt').text(); process.stdout.write(value)",
      ], { cwd: input.workspace, stdout: "pipe", stderr: "pipe" })
      const output = await new Response(child.stdout).text()
      const error = await new Response(child.stderr).text()
      if (await child.exited !== 0) throw new Error(error)
      return {
        output,
        changedFiles: [],
        capabilityRevision: "fixture-r1",
        backendId: this.id,
        modelId: input.selection.modelId,
        nativeOptions: input.selection.nativeOptions,
      }
    },
  }
  ExecutionBackends.register(backend)
  const abort = new AbortController()
  try {
    const result = await dispatchDomainExecution({
      sessionID: "adapter-session",
      runId: "adapter-run",
      workspace,
      goal: "Read source.txt",
      signal: abort.signal,
      binding: {
        schemaVersion: "domain-execution-binding-v1",
        runId: "adapter-run",
        selection: { domain: "general", skills: [] },
        policy: {
          domainId: "general", domainRevision: "general-1", skillRevisions: [],
          allowedOperations: ["read", "search"], allowedSubagentTypes: [], requiresPlan: false, demoFirst: false,
          verification: { defaultStrength: "structural", criterionTemplates: ["observation"] },
          measurement: { summarySchemaVersion: "evidence-summary-v1", requiredFields: ["observed"] },
        },
        module: { id: "general-default", revision: "1" },
        preparationStrategy: { id: "general-context", revision: "1" },
        proposalStrategy: { id: "general-direct-result", revision: "1" },
        overlays: [],
        executor: {
          id: backend.id,
          revision: "fixture-r1",
          kind: "agent_runtime",
          connectionId: backend.id,
          modelId: "fixture-model",
          options: {},
        },
      },
      preparation: {
        schemaVersion: "domain-preparation-v1",
        domainId: "general",
        mode: "read",
        goal: "Read source.txt",
        workspace,
        instructions: ["Read only and report the observed content."],
        allowedOperations: ["read", "search"],
        allowedSubagentTypes: [],
        overlays: [],
        environment: {},
      },
      proposal: { kind: "direct", dispatch: "adapter", instruction: "Read source.txt", mutationPolicy: "forbid" },
      context: {},
    })
    expect(result).toMatchObject({
      runId: "adapter-run",
      output: "controlled observation\n",
      changedFiles: [],
      adapterId: backend.id,
    })
    expect(calls).toEqual([{ runId: "adapter-run", phase: "research", cwd: workspace }])
    expect(sha256(await readFile(source, "utf8"))).toBe(before)
  } finally {
    await rm(workspace, { recursive: true, force: true })
  }
})

test("General reads an existing file, keeps the workspace immutable, and waits for Python verification", async () => {
  const root = await mkdtemp(join(tmpdir(), "base-harness-domain-general-"))
  const workspace = join(root, "workspace")
  await mkdir(workspace)
  await Bun.write(join(workspace, "source.txt"), "fixture observation\n")
  const runtime = runtimeFor(join(root, "state"))
  const host = hostFor(runtime, join(root, "plans"))
  runtime.registerDomainExecutor(async (request) => ({
    runId: request.runId,
    output: await readFile(join(request.workspace, "source.txt"), "utf8"),
    changedFiles: [],
    adapterId: request.binding.executor.id,
    modelId: request.binding.executor.modelId,
  }))
  const before = sha256(await readFile(join(workspace, "source.txt"), "utf8"))
  try {
    const opened = await host.openRun({
      sessionID: "general-integration",
      workspace,
      goal: "Read source.txt",
      defaultDomain: "general",
      trigger: "manual",
      context: {},
      domainExecutor: { id: "general-reader", revision: "1", kind: "agent_runtime", modelId: "fixture", options: {} },
    })
    expect(opened.domainPreparation).toMatchObject({ domainId: "general", mode: "read" })
    await host.stageExecutionProposal("general-integration", {
      kind: "direct", dispatch: "adapter", instruction: "Read source.txt", mutationPolicy: "forbid",
    })
    const executed = await host.proposeContract("general-integration", contract({
      goal: "Read source.txt",
      target: "source.txt",
      capability: "read",
      predicate: { type: "content_contains", value: "fixture observation" },
    }))
    expect(executed.domainResult).toMatchObject({
      runId: opened.runId,
      output: "fixture observation\n",
      changedFiles: [],
      adapterId: "general-reader",
    })
    expect(executed.evidenceCount).toBe(0)
    expect(executed.readyEligible).toBe(false)
    expect(sha256(await readFile(join(workspace, "source.txt"), "utf8"))).toBe(before)

    const verified = await runtime.verifyRoot("general-integration", "completion")
    expect(verified.outcome).toBe("ready")
    expect(verified.readyEligible).toBe(true)
    expect(verified.evidenceCount).toBeGreaterThan(0)
    expect(sha256(await readFile(join(workspace, "source.txt"), "utf8"))).toBe(before)
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(root, { recursive: true, force: true })
  }
}, 20_000)

test("General cannot become Ready when its reported result contradicts the accepted file predicate", async () => {
  const root = await mkdtemp(join(tmpdir(), "base-harness-domain-general-result-binding-"))
  const workspace = join(root, "workspace")
  await mkdir(workspace)
  await Bun.write(join(workspace, "source.txt"), "verified observation\n")
  const runtime = runtimeFor(join(root, "state"))
  const host = hostFor(runtime, join(root, "plans"))
  runtime.registerDomainExecutor(async (request) => ({
    runId: request.runId,
    output: "invented observation",
    changedFiles: [],
    adapterId: request.binding.executor.id,
    modelId: request.binding.executor.modelId,
  }))
  try {
    await host.openRun({
      sessionID: "general-result-binding",
      workspace,
      goal: "Read source.txt and report its content",
      defaultDomain: "general",
      trigger: "manual",
      context: {},
      domainExecutor: { id: "general-reader", revision: "1", kind: "agent_runtime", modelId: "fixture", options: {} },
    })
    await host.stageExecutionProposal("general-result-binding", {
      kind: "direct", dispatch: "adapter", instruction: "Read source.txt", mutationPolicy: "forbid",
    })
    const rejected = await host.proposeContract("general-result-binding", contract({
      goal: "Read source.txt and report its content",
      target: "source.txt",
      capability: "read",
      predicate: { type: "content_equals", value: "verified observation\n" },
    }))
    expect(rejected.outcome).toBe("blocked")
    expect(rejected.readyEligible).toBe(false)
    expect(rejected.failureKind).toBe("model_protocol_error")
    expect(rejected.message).toContain("DOMAIN_RESULT_MISMATCH")

    const verified = await runtime.verifyRoot("general-result-binding", "completion")
    expect(verified.outcome).toBe("blocked")
    expect(verified.readyEligible).toBe(false)
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(root, { recursive: true, force: true })
  }
}, 20_000)

test("General completion waits for a result from the current attached Run", async () => {
  const root = await mkdtemp(join(tmpdir(), "base-harness-domain-general-result-wait-"))
  const workspace = join(root, "workspace")
  await mkdir(workspace)
  await Bun.write(join(workspace, "source.txt"), "current run observation\n")
  const runtime = runtimeFor(join(root, "state"))
  const host = hostFor(runtime, join(root, "plans"))
  try {
    const opened = await host.openRun({
      sessionID: "general-result-wait",
      workspace,
      goal: "Read source.txt and report its content",
      defaultDomain: "general",
      trigger: "manual",
      context: {},
      domainExecutor: { id: "session-model", revision: "1", kind: "model_api", modelId: "fixture", options: {} },
    })
    await host.stageExecutionProposal("general-result-wait", {
      kind: "direct", dispatch: "attached", instruction: "Read source.txt", mutationPolicy: "forbid",
    })
    const accepted = await host.proposeContract("general-result-wait", contract({
      goal: "Read source.txt and report its content",
      target: "source.txt",
      capability: "read",
      predicate: { type: "content_equals", value: "current run observation\n" },
    }))
    expect(accepted.contractStatus).toBe("accepted")

    const premature = await runtime.verifyRoot("general-result-wait", "completion")
    expect(premature.outcome).not.toBe("ready")
    expect(premature.readyEligible).toBe(false)
    expect(premature.domainResult).toBeUndefined()

    await host.recordExecutionResult("general-result-wait", opened.runId, {
      output: "current run observation",
      changedFiles: [],
      adapterId: "session-model",
      modelId: "fixture",
    })
    const verified = await runtime.verifyRoot("general-result-wait", "completion")
    expect(verified.outcome).toBe("ready")
    expect(verified.readyEligible).toBe(true)
    expect(verified.domainResult?.runId).toBe(opened.runId)
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(root, { recursive: true, force: true })
  }
}, 20_000)

test("Develop sends changes through Candidate verification and commits only the verified file", async () => {
  const root = await mkdtemp(join(tmpdir(), "base-harness-domain-develop-"))
  const workspace = join(root, "workspace")
  await mkdir(workspace)
  await Bun.write(join(workspace, "input.txt"), "before\n")
  const runtime = runtimeFor(join(root, "state"))
  const host = hostFor(runtime, join(root, "plans"))
  runtime.registerWorkerExecutor(async (request) => {
    const sessionID = "develop-worker"
    runtime.orchestration.startChild({
      parentSessionID: request.rootSessionID,
      sessionID,
      subagentType: request.unit.agentType ?? "general",
      workUnitId: request.unit.id,
    })
    const routed = await runtime.orchestration.resolveWrite(sessionID, workspace, "result.txt")
    await writeFile(routed.physicalPath, "verified develop output\n")
    await runtime.finishWorker(sessionID, true)
    return { sessionID, output: "candidate produced" }
  })
  try {
    const opened = await host.openRun({
      sessionID: "develop-integration",
      workspace,
      goal: "Create result.txt",
      defaultDomain: "develop",
      trigger: "manual",
      context: {},
      execution: { adapterID: "develop-worker-adapter", modelID: "fixture", kind: "agent_runtime" },
    })
    expect(opened.domainPreparation).toMatchObject({ domainId: "develop", mode: "develop" })
    await host.stageExecutionProposal("develop-integration", {
      kind: "work_graph",
      graph: {
        units: [{
          id: "write-result",
          title: "Create result",
          instructions: "Create result.txt with the requested content",
          agentType: "general",
          claimIds: ["claim"],
          criterionIds: ["criterion"],
          dependsOn: [],
          readSet: ["input.txt"],
          writeSet: ["result.txt"],
          integrationRequests: [],
        }],
        integrationPaths: [],
      },
    }, {})
    const scheduled = await host.proposeContract("develop-integration", contract({
      goal: "Create result.txt",
      target: "result.txt",
      capability: "write",
      predicate: { type: "content_equals", value: "verified develop output\n" },
    }))
    expect(scheduled.contractStatus).toBe("accepted")
    const verified = await runtime.verifyRoot("develop-integration", "completion")
    expect(verified.workers).toEqual([
      expect.objectContaining({ workUnitId: "write-result", state: "completed", output: "candidate produced" }),
    ])
    expect(verified.outcome).toBe("ready")
    expect(verified.readyEligible).toBe(true)
    expect(await readFile(join(workspace, "result.txt"), "utf8")).toBe("verified develop output\n")
    expect(await readFile(join(workspace, "input.txt"), "utf8")).toBe("before\n")
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(root, { recursive: true, force: true })
  }
}, 20_000)

test("Hackathon composes with Develop and crosses the reviewed-plan boundary only on explicit execution", async () => {
  const root = await mkdtemp(join(tmpdir(), "base-harness-domain-hackathon-"))
  const workspace = join(root, "workspace")
  await mkdir(workspace)
  await Bun.write(join(workspace, "input.txt"), "seed\n")
  const runtime = runtimeFor(join(root, "state"))
  const host = hostFor(runtime, join(root, "plans"))
  let reviewedPlan: any
  host.registerMetaReviewer(async (request) => {
    if (request.phase === "plan") reviewedPlan = structuredClone(request.artifact)
    return { phase: request.phase, outcome: "pass", issues: [] }
  })
  let workerSequence = 0
  runtime.registerWorkerExecutor(async (request) => {
    const sessionID = `hackathon-worker-${request.unit.id}-${++workerSequence}`
    runtime.orchestration.startChild({
      parentSessionID: request.rootSessionID,
      sessionID,
      subagentType: request.unit.agentType ?? "general",
      workUnitId: request.unit.id,
    })
    const target = request.unit.id === "demo" ? "demo.txt" : "result.txt"
    const routed = await runtime.orchestration.resolveWrite(sessionID, workspace, target)
    await writeFile(routed.physicalPath, request.unit.id === "demo" ? "vertical slice\n" : "hackathon result\n")
    await runtime.finishWorker(sessionID, true)
    return { sessionID, output: `${request.unit.id} produced` }
  })
  try {
    await host.control(
      "hackathon-integration",
      { type: "skill.set", skill: "hackathon", enabled: true },
      undefined,
      workspace,
    )
    await host.control("hackathon-integration", { type: "planning.plan_once" }, undefined, workspace)
    const opened = await host.openRun({
      sessionID: "hackathon-integration",
      workspace,
      goal: "Create a demonstrable result",
      defaultDomain: "develop",
      trigger: "manual",
      context: {},
      execution: { adapterID: "hackathon-worker-adapter", modelID: "fixture", kind: "agent_runtime" },
    })
    expect(opened.domainBinding).toMatchObject({
      selection: { domain: "develop", skills: ["hackathon"] },
      overlays: [{ overlayId: "hackathon", overlayRevision: "hackathon-1" }],
    })
    expect(opened.domainPreparation.overlays).toEqual([{ id: "hackathon", revision: "hackathon-1" }])
    await host.stageExecutionProposal("hackathon-integration", {
      kind: "work_graph",
      graph: {
        units: [{
          id: "polish",
          title: "Polish result",
          instructions: "Turn the demo into the requested result",
          agentType: "general",
          claimIds: ["result-claim"],
          criterionIds: ["result-criterion"],
          dependsOn: ["demo"],
          readSet: ["demo.txt"],
          writeSet: ["result.txt"],
          integrationRequests: [],
        }, {
          id: "demo",
          title: "Build demo",
          instructions: "Build the smallest demonstrable vertical slice",
          agentType: "general",
          claimIds: ["demo-claim"],
          criterionIds: ["demo-criterion"],
          dependsOn: [],
          readSet: ["input.txt"],
          writeSet: ["demo.txt"],
          integrationRequests: [],
        }],
        integrationPaths: [],
      },
    }, {})
    const planned = await host.proposeContract("hackathon-integration", {
      goal: "Create a demonstrable result",
      criteria: [{
        criterionId: "demo-criterion",
        statement: "The vertical slice is observable",
        claimIds: ["demo-claim"],
        required: true,
        risk: "low" as const,
      }, {
        criterionId: "result-criterion",
        statement: "The requested result is observable",
        claimIds: ["result-claim"],
        required: true,
        risk: "low" as const,
      }],
      claims: [{
        claimId: "demo-claim",
        criterionIds: ["demo-criterion"],
        origin: "user" as const,
        statement: "The vertical slice is observable",
        kind: "artifact" as const,
        scope: { targets: ["demo.txt"], capabilities: ["write"], exclusions: [] },
        applicability: {},
        predicate: { type: "content_equals", value: "vertical slice\n" },
        verifierPolicy: {
          minimumStrength: "structural" as const,
          allowedVerifierIds: ["file"],
          minIndependentFamilies: 1,
        },
      }, {
        claimId: "result-claim",
        criterionIds: ["result-criterion"],
        origin: "user" as const,
        statement: "The requested result is observable",
        kind: "artifact" as const,
        scope: { targets: ["result.txt"], capabilities: ["write"], exclusions: [] },
        applicability: {},
        predicate: { type: "content_equals", value: "hackathon result\n" },
        verifierPolicy: {
          minimumStrength: "structural" as const,
          allowedVerifierIds: ["file"],
          minIndependentFamilies: 1,
        },
      }],
      constraints: [],
      interpretation: { version: 1 as const, candidates: [] },
    })
    expect(planned.planningState).toBe("plan_ready")
    expect(planned.workers).toEqual([])
    expect(await Bun.file(join(workspace, "demo.txt")).exists()).toBe(false)
    expect(await Bun.file(join(workspace, "result.txt")).exists()).toBe(false)
    expect(reviewedPlan.steps.map((step: any) => [step.id, step.priority])).toEqual([
      ["demo", "demo_required"],
      ["polish", "required"],
    ])

    const executing = await host.control(
      "hackathon-integration",
      { type: "planning.execute", planId: planned.activePlanId },
      {},
      workspace,
    )
    expect(executing.runId).not.toBe(opened.runId)
    const verified = await runtime.verifyRoot("hackathon-integration", "completion")
    expect(verified.workers.map((worker) => worker.workUnitId)).toEqual(["demo", "polish"])
    expect(verified.outcome).toBe("ready")
    expect(verified.readyEligible).toBe(true)
    expect(await readFile(join(workspace, "demo.txt"), "utf8")).toBe("vertical slice\n")
    expect(await readFile(join(workspace, "result.txt"), "utf8")).toBe("hackathon result\n")
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    await rm(root, { recursive: true, force: true })
  }
}, 30_000)
