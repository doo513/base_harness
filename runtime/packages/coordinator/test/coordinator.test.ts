import { afterEach, expect, test } from "bun:test"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import * as Orchestration from "@base-harness/core/orchestration"
import type {
  CandidateManifest,
  OpenRunInput,
  ProcessVerificationClient,
  ScopeAttestation,
  VerificationStatus,
} from "@base-harness/verification"
import { CoordinatorRuntime } from "../src"

const roots: string[] = []

afterEach(async () => {
  Orchestration.resetForTest()
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

class FakeVerifier {
  readonly runId: string
  readonly rootScopeId: string
  private current: VerificationStatus
  private candidate?: CandidateManifest

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
      evidenceRefs: [],
      candidateRefs: [],
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
  async attachCandidate(candidate: CandidateManifest) { this.candidate = candidate; return this.current }
  async reopenScope() { this.candidate = undefined; return this.current }
  async commitCandidate(_attestation: ScopeAttestation) { return this.current }
  async verify(_reason: string, scopeId = this.rootScopeId) {
    if (scopeId !== this.rootScopeId && this.candidate) {
      this.current = {
        ...this.current,
        scopeId,
        outcome: "scope_verified",
        scopeAttestation: {
          candidateId: this.candidate.candidateId,
          candidateRevision: this.candidate.revision,
          patchHash: this.candidate.patchHash,
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

  Orchestration.beginPrompt({
    sessionID: "root",
    workspace,
    goal: "Implement three independent modules in parallel",
  })
  Orchestration.registerContract("root", ["claim-a", "claim-b", "claim-c"], ["criterion-a", "criterion-b", "criterion-c"])

  const runtime = new CoordinatorRuntime(async (input) => new FakeVerifier(input) as unknown as ProcessVerificationClient)
  await runtime.openRun({ sessionID: "root", workspace, goal: "Implement three independent modules", configuredProfile: "fast" })
  let active = 0
  let maximum = 0
  runtime.registerWorkerExecutor(async ({ rootSessionID, unit }) => {
    active += 1
    maximum = Math.max(maximum, active)
    const sessionID = "worker-" + unit.id
    Orchestration.startChild({
      parentSessionID: rootSessionID,
      sessionID,
      subagentType: unit.agentType ?? "general",
      workUnitId: unit.id,
    })
    const target = await Orchestration.resolveWrite(sessionID, workspace, unit.writeSet[0]!)
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
  expect(maximum).toBe(2)
  expect(status.workers.map((worker) => worker.state)).toEqual(["completed", "completed", "completed"])
  expect(await readFile(join(workspace, "a.txt"), "utf8")).toBe("a")
  expect(await readFile(join(workspace, "b.txt"), "utf8")).toBe("b")
  expect(await readFile(join(workspace, "c.txt"), "utf8")).toBe("c")
})
