import { expect, test } from "bun:test"
import { mkdtemp, mkdir, readFile, rm, writeFile, symlink } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, relative } from "node:path"
import * as Workspace from "../src/orchestration"

async function fixture(run: (value: {
  workspace: string; state: string; original: string; overlay: string;
  candidate: Workspace.CandidateManifest; materialized: string;
}) => Promise<void>, materialize = true) {
  const directory = await mkdtemp(join(tmpdir(), "harness-candidate-integrity-"))
  const workspace = join(directory, "workspace")
  const state = join(directory, "state")
  await mkdir(workspace)
  const store = new Workspace.WorkspaceCandidateStore()
  await Workspace.withWorkspaceCandidateStore(store, async () => {
    const oldLocal = process.env.LOCALAPPDATA
    const oldXdg = process.env.XDG_STATE_HOME
    try {
      process.env.LOCALAPPDATA = state
      process.env.XDG_STATE_HOME = state
      Workspace.beginPrompt({ sessionID: "root", workspace, goal: "Update result", exploration: "manual" })
      Workspace.setRunIdentity("root", "fixture-run")
    } finally {
      if (oldLocal === undefined) delete process.env.LOCALAPPDATA
      else process.env.LOCALAPPDATA = oldLocal
      if (oldXdg === undefined) delete process.env.XDG_STATE_HOME
      else process.env.XDG_STATE_HOME = oldXdg
    }
    try {
      const original = join(workspace, "result.txt")
      await writeFile(original, "before")
      Workspace.registerContract("root", ["claim"], ["criterion"])
      Workspace.beginPlanning("root")
      await Workspace.acceptWorkGraph("root", {
        units: [{ id: "unit", title: "Update", instructions: "Write after",
          claimIds: ["claim"], criterionIds: ["criterion"], dependsOn: [],
          readSet: ["result.txt"], writeSet: ["result.txt"], integrationRequests: [] }],
        integrationPaths: [],
      })
      Workspace.startChild({ parentSessionID: "root", sessionID: "worker", subagentType: "general", workUnitId: "unit" })
      const route = await Workspace.resolveWrite("worker", workspace, "result.txt")
      await writeFile(route.physicalPath, "after")
      const candidate = (await Workspace.finishChild("worker", true))!
      expect(Workspace.snapshot("root")?.candidates).toHaveLength(1)
      const materialized = materialize ? await Workspace.materializeCandidate(candidate.candidateId) : ""
      await run({ workspace, state, original, overlay: route.physicalPath, candidate, materialized })
    } finally {
      await store.flushPersistence()
      store.clear()
      expect(relative(tmpdir(), directory).startsWith("..")).toBe(false)
      await rm(directory, { recursive: true, force: true })
    }
  })
}

const attestation = (candidate: Workspace.CandidateManifest) => ({
  candidateId: candidate.candidateId, candidateRevision: candidate.revision, patchHash: candidate.patchHash,
})

test("prepared workers cannot add or change overlay writes until explicit repair", async () => {
  await fixture(async ({ workspace, candidate }) => {
    expect(() => Workspace.assertToolAllowed("worker", "write")).toThrow("frozen")
    await expect(Workspace.resolveWrite("worker", workspace, "result.txt")).rejects.toMatchObject({ code: "PHASE_VIOLATION" })
    await Workspace.releaseCandidateWorkspace(candidate.candidateId)
    Workspace.reopenScope("worker")
    Workspace.startChild({ parentSessionID: "root", sessionID: "worker", subagentType: "general", workUnitId: "unit" })
    await expect(Workspace.resolveWrite("worker", workspace, "result.txt")).resolves.toMatchObject({ overlay: true })
  })
})

for (const target of ["overlay", "materialized"] as const) {
  test("tampered " + target + " bytes cannot commit an attested candidate", async () => {
    await fixture(async (value) => {
      await writeFile(target === "overlay" ? value.overlay : join(value.materialized, "result.txt"), "tampered")
      await expect(Workspace.commitCandidate(value.candidate.candidateId, attestation(value.candidate)))
        .rejects.toMatchObject({ code: "WORKSPACE_CONFLICT" })
      expect(await readFile(value.original, "utf8")).toBe("before")
    })
  })
}

test("missing verification workspace is not treated as verified", async () => {
  await fixture(async ({ candidate, original }) => {
    await expect(Workspace.commitCandidate(candidate.candidateId, attestation(candidate)))
      .rejects.toMatchObject({ code: "PHASE_VIOLATION" })
    expect(await readFile(original, "utf8")).toBe("before")
  }, false)
})

test("a replaced candidate directory cannot cross a symlink or Windows junction boundary", async () => {
  await fixture(async ({ materialized, state, candidate, original }) => {
    const outside = join(state, "outside")
    await mkdir(outside)
    await writeFile(join(outside, "result.txt"), "after")
    expect(relative(state, materialized).startsWith("..")).toBe(false)
    await rm(materialized, { recursive: true })
    await symlink(outside, materialized, process.platform === "win32" ? "junction" : "dir")
    await expect(Workspace.commitCandidate(candidate.candidateId, attestation(candidate)))
      .rejects.toMatchObject({ code: "OWNERSHIP_VIOLATION" })
    expect(await readFile(original, "utf8")).toBe("before")
  })
})

test("an existing sibling staging file is neither overwritten nor deleted", async () => {
  await fixture(async ({ candidate, original }) => {
    const sibling = original + ".base-harness-" + candidate.candidateId.replace(/[^A-Za-z0-9_.-]/g, "_") + ".tmp"
    await writeFile(sibling, "external data")
    await expect(Workspace.commitCandidate(candidate.candidateId, attestation(candidate))).rejects.toThrow()
    expect(await readFile(original, "utf8")).toBe("before")
    expect(await readFile(sibling, "utf8")).toBe("external data")
  })
})
