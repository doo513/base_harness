import { afterEach, expect, test } from "bun:test"
import { createHash } from "node:crypto"
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import type {
  CandidateManifest,
  GoalContract,
  OpenRunInput,
  ProcessVerificationClient,
  ScopeAttestation,
  VerificationStatus,
} from "@base-harness/verification"
import { CoordinatorRuntime, RunRepository } from "../src"

const cleanups: Array<() => Promise<void>> = []

afterEach(async () => {
  while (cleanups.length) await cleanups.pop()!()
})

class LifecycleVerifier {
  readonly runId: string
  readonly rootScopeId: string
  rootVerificationCalls = 0
  private current: VerificationStatus
  private readonly candidates = new Map<string, CandidateManifest>()

  constructor(input: OpenRunInput) {
    this.runId = input.runId
    this.rootScopeId = input.scopeId
    this.current = {
      state: "open",
      goal: input.goalSources[0]?.text ?? "",
      runId: input.runId,
      scopeId: input.scopeId,
      rootScopeId: input.scopeId,
      contractStatus: "missing",
      criterionResults: [],
      claimResults: [],
      evidenceFamilies: [],
      evidenceRefs: [],
      candidateRefs: [],
      readyRef: null,
      readyEligible: false,
      maxSameFailureRepairs: 2,
      configuredProfile: input.configuredProfile,
      effectiveProfile: input.effectiveProfile,
    }
  }

  snapshot() { return this.current }
  subscribe(listener: (status: VerificationStatus) => void) { listener(this.current); return () => undefined }
  async open() { return this.current }
  async openScope(scopeId: string) { return { ...this.current, scopeId } }
  async proposeContract(contract: GoalContract) {
    this.current = { ...this.current, contractStatus: "accepted", goalContract: contract }
    return this.current
  }
  async amendContract(contract: GoalContract) { return this.proposeContract(contract) }
  async openAction() { return { actionId: "action", status: this.current } }
  async closeAction() { return this.current }
  async observe() { return this.current }
  async attachCandidate(candidate: CandidateManifest) {
    this.candidates.set(candidate.scopeId, candidate)
    return this.current
  }
  async reopenScope(scopeId: string) { this.candidates.delete(scopeId); return this.current }
  async commitCandidate(_attestation: ScopeAttestation) { return this.current }
  async verify(_reason: string, scopeId = this.rootScopeId) {
    const candidate = this.candidates.get(scopeId)
    if (scopeId !== this.rootScopeId && candidate) {
      return {
        ...this.current,
        scopeId,
        outcome: "scope_verified" as const,
        scopeAttestation: {
          candidateId: candidate.candidateId,
          candidateRevision: candidate.revision,
          patchHash: candidate.patchHash,
        },
      }
    }
    this.rootVerificationCalls += 1
    this.current = {
      ...this.current,
      scopeId: this.rootScopeId,
      state: "ready",
      outcome: "ready",
      readyEligible: true,
    }
    return this.current
  }
  async status() { return this.current }
  async close() { return this.current }
  async dispose() {}
}

const proposal = {
  goal: "Change result.txt",
  criteria: [{
    criterionId: "criterion", statement: "Write after", claimIds: ["claim"], required: true, risk: "low" as const,
  }],
  claims: [{
    claimId: "claim", criterionIds: ["criterion"], origin: "user" as const,
    statement: "Write after", kind: "artifact" as const,
    scope: { targets: ["result.txt"], capabilities: ["write"], exclusions: [] },
    predicate: { type: "content_equals" as const, value: "after" },
    verifierPolicy: { minimumStrength: "structural" as const, allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
  }],
}

async function fixture() {
  const directory = await mkdtemp(join(tmpdir(), "coordinator-integration-lifecycle-"))
  const workspace = join(directory, "workspace")
  const state = join(directory, "state")
  await mkdir(workspace)
  await mkdir(state)
  await writeFile(join(workspace, "result.txt"), "before")
  const stateKeys = ["LOCALAPPDATA", "XDG_STATE_HOME"] as const
  const previousState = new Map(stateKeys.map(key => [key, process.env[key]]))
  for (const key of stateKeys) process.env[key] = state
  const verifiers: LifecycleVerifier[] = []
  const runtime = new CoordinatorRuntime(async input => {
    const verifier = new LifecycleVerifier(input)
    verifiers.push(verifier)
    return verifier as unknown as ProcessVerificationClient
  }, { repository: new RunRepository<any>({ stateDirectory: state, persistent: false }) })
  cleanups.push(async () => {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    for (const [key, value] of previousState) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    const target = relative(tmpdir(), directory)
    if (target.startsWith("..") || isAbsolute(target)) throw new Error("Unsafe fixture cleanup")
    await rm(directory, { recursive: true, force: true })
  })
  return { runtime, verifiers, workspace }
}

function registerWorker(runtime: CoordinatorRuntime, workspace: string) {
  runtime.registerWorkerExecutor(async ({ rootSessionID, unit }) => {
    const sessionID = "worker-" + unit.id
    runtime.orchestration.startChild({
      parentSessionID: rootSessionID,
      sessionID,
      subagentType: "general",
      workUnitId: unit.id,
    })
    const target = await runtime.orchestration.resolveWrite(sessionID, workspace, "result.txt")
    await writeFile(target.physicalPath, "after")
    await runtime.finishWorker(sessionID, true)
    return { sessionID }
  })
}

const graph = {
  units: [{
    id: "unit", title: "Change result", instructions: "Write after",
    claimIds: ["claim"], criterionIds: ["criterion"], dependsOn: [],
    readSet: ["result.txt"], writeSet: ["result.txt"], integrationRequests: [],
  }],
  integrationPaths: [],
}

test("reviewed plan execution invokes root integration even without requested merge paths", async () => {
  const { runtime, verifiers, workspace } = await fixture()
  const planning = await runtime.openRun({ sessionID: "root", workspace, goal: proposal.goal, trigger: "manual" })
  await runtime.proposeContract("root", proposal)
  runtime.beginPlanning("root")
  await runtime.beginPlanExecution("root", {
    planningRunId: planning.runId,
    planId: "reviewed-plan",
    planRevision: 1,
    goalContractHash: createHash("sha256").update(JSON.stringify(proposal)).digest("hex"),
    context: { fixture: true },
  })
  let integrations = 0
  runtime.registerIntegrationExecutor(async () => { integrations += 1 })
  registerWorker(runtime, workspace)

  await runtime.acceptWorkGraph("root", graph, { fixture: true })
  const status = await runtime.verifyRoot("root", "completion")

  expect(integrations).toBe(1)
  expect(verifiers.at(-1)?.rootVerificationCalls).toBe(1)
  expect(status.outcome).toBe("ready")
  expect(status.readyEligible).toBe(true)
})

for (const scenario of ["missing", "failure"] as const) {
  test(`root integration ${scenario} is terminal and fails closed`, async () => {
    const { runtime, verifiers, workspace } = await fixture()
    await runtime.openRun({ sessionID: "root", workspace, goal: proposal.goal, trigger: "manual" })
    await runtime.proposeContract("root", proposal)
    runtime.beginPlanning("root")
    let integrations = 0
    if (scenario === "failure") {
      runtime.registerIntegrationExecutor(async () => {
        integrations += 1
        throw new Error("injected integration failure")
      })
    }
    registerWorker(runtime, workspace)

    await runtime.acceptWorkGraph("root", graph, { fixture: true })
    const status = await runtime.verifyRoot("root", "completion")

    expect(integrations).toBe(scenario === "failure" ? 1 : 0)
    expect(verifiers[0]?.rootVerificationCalls).toBe(0)
    expect(status.outcome).toBe("blocked")
    expect(status.failureKind).toBe("harness_error")
    expect(status.readyEligible).toBe(false)
    expect((await runtime.verifyRoot("root", "manual")).outcome).toBe("blocked")
    expect(verifiers[0]?.rootVerificationCalls).toBe(0)
  })
}
