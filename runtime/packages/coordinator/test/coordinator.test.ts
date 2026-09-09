import { afterEach, expect, spyOn, test } from "bun:test"
import { promises as fs } from "node:fs"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import * as Orchestration from "@base-harness/workspace/orchestration"
import type {
  CandidateManifest,
  OpenRunInput,
  ProcessVerificationClient,
  ScopeAttestation,
  VerificationStatus,
} from "@base-harness/verification"
import { CoordinatorRuntime } from "../src"

const roots: string[] = []
const runtimes: Array<{ runtime: CoordinatorRuntime; workspace: string }> = []

afterEach(async () => {
  for (const { runtime, workspace } of runtimes.splice(0)) {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
  }
  await Orchestration.flushPersistence()
  Orchestration.resetForTest()
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

class FakeVerifier {
  readonly runId: string
  readonly rootScopeId: string
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
      contractStatus: "accepted",
      goalContract: input.goalContract,
      criterionResults: [],
      claimResults: [],
      evidenceFamilies: [],
      evidenceRefs: [{ artifactType: "claim_evidence", path: "/fixture/evidence.json", sha256: "a".repeat(64), trust: "verifier_observed" }],
      candidateRefs: [{ artifactType: "candidate_manifest", path: "/fixture/candidate.json", sha256: "b".repeat(64), trust: "verifier_observed" }],
      readyRef: null,
      maxSameFailureRepairs: 2,
      configuredProfile: input.configuredProfile,
      effectiveProfile: input.effectiveProfile,
    }
  }

  snapshot() { return this.current }
  subscribe(listener: (status: VerificationStatus) => void) { listener(this.current); return () => undefined }
  async open() { return this.current }
  async openScope(scopeId: string) { this.current = { ...this.current, scopeId }; return this.current }
  async proposeContract(contract: VerificationStatus["goalContract"]) { this.current = { ...this.current, goalContract: contract }; return this.current }
  async amendContract(contract: VerificationStatus["goalContract"]) { return this.proposeContract(contract) }
  async openAction() { return { actionId: "action", status: this.current } }
  async closeAction() { return this.current }
  async observe() { return this.current }
  async attachCandidate(candidate: CandidateManifest) { this.candidates.set(candidate.scopeId, candidate); return this.current }
  async reopenScope(scopeId: string) { this.candidates.delete(scopeId); return this.current }
  async commitCandidate(_attestation: ScopeAttestation) { return this.current }
  async verify(_reason: string, scopeId = this.rootScopeId) {
    const candidate = this.candidates.get(scopeId)
    if (scopeId !== this.rootScopeId && candidate) {
      this.current = {
        ...this.current,
        scopeId,
        outcome: "scope_verified",
        scopeAttestation: {
          candidateId: candidate.candidateId,
          candidateRevision: candidate.revision,
          patchHash: candidate.patchHash,
        },
      }
    }
    return this.current
  }
  async status() { return this.current }
  async close() { return this.current }
  async dispose() {}
}

test("Coordinator queues a third unit while running at most two and commits only attested candidates", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-coordinator-"))
  roots.push(workspace)
  for (const name of ["a.txt", "b.txt", "c.txt"]) await writeFile(join(workspace, name), "before", "utf8")

  const runtime = new CoordinatorRuntime(async (input) => new FakeVerifier(input) as unknown as ProcessVerificationClient)
  runtimes.push({ runtime, workspace })
  runtime.orchestration.beginPrompt({
    sessionID: "root",
    workspace,
    goal: "Implement three independent modules in parallel",
  })
  runtime.orchestration.registerContract("root", ["claim-a", "claim-b", "claim-c"], ["criterion-a", "criterion-b", "criterion-c"])
  await runtime.openRun({ sessionID: "root", workspace, goal: "Implement three independent modules", configuredProfile: "fast" })
  await runtime.proposeContract("root", {
    goal: "Implement three independent modules",
    criteria: ["a", "b", "c"].map((id) => ({
      criterionId: "criterion-" + id, statement: "Write " + id, claimIds: ["claim-" + id], required: true, risk: "low" as const,
    })),
    claims: ["a", "b", "c"].map((id) => ({
      claimId: "claim-" + id, criterionIds: ["criterion-" + id], origin: "user" as const,
      statement: "Write " + id, kind: "artifact" as const,
      scope: { targets: [id + ".txt"], capabilities: ["write"], exclusions: [] },
      predicate: { type: "exists" },
      verifierPolicy: { minimumStrength: "structural" as const, allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
    })),
  })
  let active = 0
  let maximum = 0
  runtime.registerWorkerExecutor(async ({ rootSessionID, unit }) => {
    active += 1
    maximum = Math.max(maximum, active)
    const sessionID = "worker-" + unit.id
    runtime.orchestration.startChild({
      parentSessionID: rootSessionID,
      sessionID,
      subagentType: unit.agentType ?? "general",
      workUnitId: unit.id,
    })
    const target = await runtime.orchestration.resolveWrite(sessionID, workspace, unit.writeSet[0]!)
    await Bun.sleep(20)
    await writeFile(target.physicalPath, unit.id, "utf8")
    await runtime.finishWorker(sessionID, true)
    active -= 1
    return { sessionID }
  })

  await runtime.acceptWorkGraph(
    "root",
    {
      units: ["a", "b", "c"].map((id) => ({
        id,
        title: "Unit " + id,
        instructions: "Write " + id,
        agentType: "general",
        claimIds: ["claim-" + id],
        criterionIds: ["criterion-" + id],
        dependsOn: [],
        readSet: [id + ".txt"],
        writeSet: [id + ".txt"],
        integrationRequests: [],
      })),
      integrationPaths: [],
    },
    {},
  )

  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (runtime.status("root").workers.every((worker) => worker.state === "completed")) break
    await Bun.sleep(10)
  }
  const status = runtime.status("root")
  expect(status.evidenceRefs).toEqual(["/fixture/evidence.json"])
  expect(status.candidateRefs).toEqual(["/fixture/candidate.json"])
  expect(maximum).toBe(2)
  expect(status.workers.map((worker) => worker.state)).toEqual(["completed", "completed", "completed"])
  expect(await readFile(join(workspace, "a.txt"), "utf8")).toBe("a")
  expect(await readFile(join(workspace, "b.txt"), "utf8")).toBe("b")
  expect(await readFile(join(workspace, "c.txt"), "utf8")).toBe("c")
})

test("Coordinator reports materialization I/O as harness_error and clears completion authority", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-copy-failure-"))
  roots.push(workspace)
  const target = join(workspace, "result.txt")
  await writeFile(target, "before")
  const runtime = new CoordinatorRuntime(async input => new FakeVerifier(input) as unknown as ProcessVerificationClient)
  runtimes.push({ runtime, workspace })
  runtime.orchestration.beginPrompt({ sessionID: "root", workspace, goal: "Write after", exploration: "manual" })
  await runtime.openRun({ sessionID: "root", workspace, goal: "Write after", trigger: "manual" })
  await runtime.proposeContract("root", {
    goal: "Write after",
    criteria: [{ criterionId: "criterion", statement: "Write after", claimIds: ["claim"], required: true, risk: "low" }],
    claims: [{
      claimId: "claim", criterionIds: ["criterion"], origin: "user", statement: "Write after", kind: "artifact",
      scope: { targets: ["result.txt"], capabilities: ["write"], exclusions: [] },
      predicate: { type: "content_equals", value: "after" },
      verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
    }],
  })
  runtime.orchestration.beginPlanning("root")
  const copy = fs.cp.bind(fs)
  const copySpy = spyOn(fs, "cp").mockImplementation(async (source, destination, options) => {
    if (String(source).toLowerCase() === workspace.toLowerCase()) {
      throw Object.assign(new Error("injected copy denial"), { code: "EACCES" })
    }
    return copy(source, destination, options)
  })
  try {
    runtime.registerWorkerExecutor(async ({ rootSessionID, unit }) => {
      runtime.orchestration.startChild({ parentSessionID: rootSessionID, sessionID: "worker", subagentType: "general", workUnitId: unit.id })
      const route = await runtime.orchestration.resolveWrite("worker", workspace, "result.txt")
      await writeFile(route.physicalPath, "after")
      await runtime.finishWorker("worker", true)
      return { sessionID: "worker" }
    })
    await runtime.acceptWorkGraph("root", {
      units: [{
        id: "unit", title: "Update", instructions: "Write after", claimIds: ["claim"], criterionIds: ["criterion"],
        dependsOn: [], readSet: ["result.txt"], writeSet: ["result.txt"], integrationRequests: [],
      }], integrationPaths: [],
    }, {})
    const status = await runtime.verifyRoot("root", "completion")
    expect(status.workers[0]?.state).toBe("failed")
    expect(status.failureKind).toBe("harness_error")
    expect(status.readyEligible).toBe(false)
    expect(status.message).toContain("Candidate materialization failed")
    expect(await readFile(target, "utf8")).toBe("before")
  } finally {
    copySpy.mockRestore()
  }
})
