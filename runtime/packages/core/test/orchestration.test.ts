import { afterEach, expect, test } from "bun:test"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import * as Orchestration from "../src/orchestration"

const roots: string[] = []

afterEach(async () => {
  Orchestration.resetForTest()
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

async function fixture() {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-orchestration-"))
  roots.push(workspace)
  const target = join(workspace, "result.txt")
  await writeFile(target, "before", "utf8")
  Orchestration.beginPrompt({
    sessionID: "root",
    workspace,
    goal: "Refactor the complete module architecture with parallel implementation units",
  })
  Orchestration.registerContract("root", ["claim-1"], ["criterion-1"])
  await Orchestration.acceptWorkGraph("root", {
    units: [
      {
        id: "unit-1",
        title: "Update result",
        instructions: "Write the verified result into result.txt.",
        agentType: "general",
        claimIds: ["claim-1"],
        criterionIds: ["criterion-1"],
        dependsOn: [],
        readSet: ["result.txt"],
        writeSet: ["result.txt"],
        integrationRequests: [],
      },
    ],
    integrationPaths: [],
  })
  Orchestration.startChild({
    parentSessionID: "root",
    sessionID: "worker-1",
    subagentType: "general",
    workUnitId: "unit-1",
  })
  const mapped = await Orchestration.resolveWrite("worker-1", workspace, target)
  await writeFile(mapped.physicalPath, "after", "utf8")
  const candidate = await Orchestration.finishChild("worker-1", true)
  if (!candidate) throw new Error("candidate was not prepared")
  return { workspace, target, candidate }
}

test("worker output remains isolated until matching verifier attestation commits it", async () => {
  const { target, candidate } = await fixture()
  expect(await readFile(target, "utf8")).toBe("before")
  const result = await Orchestration.commitCandidate(candidate.candidateId, {
    candidateId: candidate.candidateId,
    candidateRevision: candidate.revision,
    patchHash: candidate.patchHash,
  })
  expect(result.scopeVerified).toBe(true)
  expect(await readFile(target, "utf8")).toBe("after")
})

test("mismatched attestation cannot commit a candidate", async () => {
  const { target, candidate } = await fixture()
  await expect(
    Orchestration.commitCandidate(candidate.candidateId, {
      candidateId: candidate.candidateId,
      candidateRevision: candidate.revision,
      patchHash: "0".repeat(64),
    }),
  ).rejects.toMatchObject({ code: "PHASE_VIOLATION" })
  expect(await readFile(target, "utf8")).toBe("before")
})

test("base hash conflict blocks commit without overwriting external changes", async () => {
  const { target, candidate } = await fixture()
  await writeFile(target, "external", "utf8")
  await expect(
    Orchestration.commitCandidate(candidate.candidateId, {
      candidateId: candidate.candidateId,
      candidateRevision: candidate.revision,
      patchHash: candidate.patchHash,
    }),
  ).rejects.toMatchObject({ code: "WORKSPACE_CONFLICT" })
  expect(await readFile(target, "utf8")).toBe("external")
})
