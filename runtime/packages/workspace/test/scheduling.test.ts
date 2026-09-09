import { expect, test } from "bun:test"
import { mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import * as Workspace from "../src/orchestration"

test("a verified worker frees the queue while another candidate is being verified", async () => {
  const directory = await mkdtemp(join(tmpdir(), "harness-worker-phase-"))
  const store = new Workspace.WorkspaceCandidateStore()
  await Workspace.withWorkspaceCandidateStore(store, async () => {
    try {
      Workspace.beginPrompt({ sessionID: "root", workspace: directory, goal: "three files", exploration: "manual" })
      Workspace.registerContract("root", ["a", "b", "c"], ["ca", "cb", "cc"])
      Workspace.beginPlanning("root")
      await Workspace.acceptWorkGraph("root", {
        units: ["a", "b", "c"].map((id) => ({
          id, title: id, instructions: "Write " + id, claimIds: [id], criterionIds: ["c" + id],
          dependsOn: [], readSet: [], writeSet: [id + ".txt"], integrationRequests: [],
        })),
        integrationPaths: [],
      })
      const candidates = []
      for (const id of ["a", "b"]) {
        Workspace.startChild({ parentSessionID: "root", sessionID: id, subagentType: "general", workUnitId: id })
        const route = await Workspace.resolveWrite(id, directory, id + ".txt")
        await writeFile(route.physicalPath, id)
        candidates.push((await Workspace.finishChild(id, true))!)
      }
      const first = candidates[0]!
      await Workspace.materializeCandidate(first.candidateId)
      await Workspace.commitCandidate(first.candidateId, {
        candidateId: first.candidateId, candidateRevision: first.revision, patchHash: first.patchHash,
      })
      Workspace.markCandidateVerifying(candidates[1]!.candidateId)
      expect(Workspace.snapshot("root")?.phase).toBe("scope_verifying")
      expect(() => Workspace.startChild({
        parentSessionID: "root", sessionID: "c", subagentType: "general", workUnitId: "c",
      })).not.toThrow()
      expect(() => Workspace.startChild({
        parentSessionID: "root", sessionID: "duplicate-a", subagentType: "general", workUnitId: "a",
      })).toThrow()
    } finally {
      await store.flushPersistence()
      store.clear()
      await rm(directory, { recursive: true, force: true })
    }
  })
})
