import { expect, test } from "bun:test"
import { promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"
import { writeAtomicSnapshot } from "@base-harness/workspace/snapshot-persistence"
import { RunRepository } from "../src/run-repository"
import type { HarnessStatus } from "../src/contracts"

async function temporary() {
  return fs.mkdtemp(path.join(os.tmpdir(), "base-harness-phase34-"))
}
async function cleanup(directory: string) {
  const resolved = path.resolve(directory)
  if (path.dirname(resolved) !== path.resolve(os.tmpdir()) || !path.basename(resolved).startsWith("base-harness-phase34-")) {
    throw new Error("Refusing cleanup outside the test scratch directory")
  }
  await fs.rm(resolved, { recursive: true, force: true })
}

function status(runId: string): HarnessStatus {
  return {
    sessionID: "session-" + runId, runId, workspace: "fixture", goal: "fixture",
    phase: "planning", workers: [], activeCount: 0, queuedCount: 0,
    verificationState: "inactive", missingEvidence: [], repairCount: 0, maxSameFailureRepairs: 2,
    evidenceCount: 0, candidateCount: 0, evidenceRefs: [], candidateRefs: [], readyEligible: false,
    metrics: { observedActions: 0, workers: 0, activeWorkers: 0, repairs: 0, evidence: 0, sandboxRuns: 0 },
  }
}

test("repository failure is sticky for its run but does not poison the shared write queue", async () => {
  const directory = await temporary()
  let badWrites = 0
  const repository = new RunRepository({ stateDirectory: directory }, async (target, body, options) => {
    if (path.basename(target) === "bad.json") {
      badWrites++
      throw new Error("failed run snapshot")
    }
    return writeAtomicSnapshot(target, body, options)
  })
  try {
    await fs.writeFile(path.join(directory, "bad.json"), '{"old":true}')
    const results = await Promise.allSettled([
      repository.persist(status("bad"), false), repository.persist(status("good"), false),
    ])
    expect(results.map(result => result.status)).toEqual(["rejected", "fulfilled"])
    await expect(repository.persist(status("bad"), false)).rejects.toThrow("failed run snapshot")
    expect(badWrites).toBe(1)
    expect(await fs.readFile(path.join(directory, "bad.json"), "utf8")).toBe('{"old":true}')
    const good = JSON.parse(await fs.readFile(path.join(directory, "good.json"), "utf8"))
    expect(good.runId).toBe("good")
    expect(good.phase).toBe("planning")
    expect(good.goal).toBeUndefined()
  } finally { await cleanup(directory) }
})
