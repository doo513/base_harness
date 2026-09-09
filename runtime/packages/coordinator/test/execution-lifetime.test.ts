import { expect, test } from "bun:test"
import { mkdtemp, writeFile, readFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import type { ProcessVerificationClient, VerificationStatus } from "@base-harness/verification"
import { CoordinatorRuntime, type WorkerExecutionRequest } from "../src"

async function setup() {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-run-lifetime-"))
  const runtime = new CoordinatorRuntime(async (input) => {
    let status = {
      state: "open", runId: input.runId, scopeId: input.scopeId, rootScopeId: input.scopeId,
      goal: input.goalSources[0]?.text ?? "", contractStatus: "accepted",
      criterionResults: [], claimResults: [], evidenceFamilies: [], evidenceRefs: [], candidateRefs: [],
      maxSameFailureRepairs: 2,
    } as VerificationStatus
    return {
      snapshot: () => status,
      subscribe: () => () => {},
      proposeContract: async (goalContract: VerificationStatus["goalContract"]) => (status = { ...status, goalContract }),
      dispose: async () => {},
      close: async () => status,
    } as unknown as ProcessVerificationClient
  })
  const stream = new AbortController()
  const context = { abort: stream.signal }
  await runtime.openRun({ sessionID: "root", workspace, goal: "Update independent files", trigger: "manual", context })
  await runtime.proposeContract("root", {
    goal: "Update independent files",
    criteria: ["a", "b"].map(id => ({
      criterionId: "criterion-" + id, statement: "Update " + id, claimIds: ["claim-" + id], required: true, risk: "low",
    })),
    claims: ["a", "b"].map(id => ({
      claimId: "claim-" + id, criterionIds: ["criterion-" + id], origin: "user", statement: "Update " + id,
      kind: "artifact", scope: { targets: [id + ".txt"], capabilities: ["write"], exclusions: [] },
      predicate: { type: "content_equals", value: "after" },
      verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
    })),
  })
  runtime.beginPlanning("root")
  const requests: WorkerExecutionRequest[] = []
  const stopped: Promise<void>[] = []
  let bothStarted!: () => void
  const started = new Promise<void>(resolve => { bothStarted = resolve })
  runtime.registerWorkerExecutor(async request => {
    requests.push(request)
    let stop!: () => void
    stopped.push(new Promise<void>(resolve => { stop = resolve }))
    const cancelled = new Promise<void>(resolve => {
      request.signal.addEventListener("abort", () => resolve(), { once: true })
      if (request.signal.aborted) resolve()
    })
    if (requests.length === 2) bothStarted()
    await cancelled
    stop()
    throw new Error("Fixture run cancelled")
  })
  for (const id of ["a", "b"]) await writeFile(join(workspace, id + ".txt"), "before")
  await runtime.acceptWorkGraph("root", {
    units: ["a", "b"].map(id => ({
      id, title: id, instructions: "Update " + id, claimIds: ["claim-" + id], criterionIds: ["criterion-" + id],
      dependsOn: [], readSet: [id + ".txt"], writeSet: [id + ".txt"], integrationRequests: [],
    })),
    integrationPaths: [],
  }, context)
  await started
  return { workspace, runtime, stream, requests, stopped }
}

test("workers outlive the parent stream but cancel with their Coordinator run", async () => {
  const { workspace, runtime, stream, requests, stopped } = await setup()
  try {
    expect(requests[0]!.signal).toBe(requests[1]!.signal)
    expect(requests[0]!.signal).not.toBe(stream.signal)
    stream.abort()
    expect(requests.every(request => !request.signal.aborted)).toBe(true)
    expect(runtime.status("root").activeCount).toBe(2)
    const status = await runtime.cancel("root")
    await Promise.all(stopped)
    expect(requests.every(request => request.signal.aborted)).toBe(true)
    expect(status.phase).toBe("interrupted")
    expect(status.readyEligible).toBe(false)
    expect(await readFile(join(workspace, "a.txt"), "utf8")).toBe("before")
    expect(await readFile(join(workspace, "b.txt"), "utf8")).toBe("before")
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
  }
})

test("workspace disposal aborts every in-flight worker and removes completion authority", async () => {
  const { workspace, runtime, requests, stopped } = await setup()
  await runtime.closeWorkspace(workspace)
  await Promise.all(stopped)
  expect(requests.every(request => request.signal.aborted)).toBe(true)
  expect(runtime.status("root").phase).toBe("inactive")
  expect(runtime.status("root").readyEligible).toBe(false)
  runtime.resetForTest()
})
