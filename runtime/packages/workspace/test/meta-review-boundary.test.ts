import { expect, test } from "bun:test"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import * as O from "../src/orchestration"

async function fixture(body: (workspace: string) => Promise<void>, phase: "direct" | "exploration" | "planning" = "direct") {
  const directory = await mkdtemp(join(tmpdir(), "harness-meta-scope-"))
  const workspace = join(directory, "workspace"), state = join(directory, "state")
  await mkdir(workspace)
  await writeFile(join(workspace, "input.txt"), "unchanged")
  const keys = ["LOCALAPPDATA", "XDG_STATE_HOME"]
  const old = new Map(keys.map(key => [key, process.env[key]]))
  for (const key of keys) process.env[key] = state
  const store = new O.WorkspaceCandidateStore()
  try {
    await O.withWorkspaceCandidateStore(store, async () => {
      O.beginPrompt({ sessionID: "root", workspace, goal: "Inspect input.txt", exploration: phase === "exploration" ? "always" : "manual" })
      if (phase === "planning") {
        O.registerContract("root", ["claim"], ["criterion"])
        O.beginPlanning("root")
      }
      try { await body(workspace) } finally { await O.flushPersistence(); store.clear() }
    })
  } finally {
    for (const [key, value] of old) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    const rel = relative(tmpdir(), directory)
    if (rel.startsWith("..") || isAbsolute(rel)) throw new Error("Unsafe fixture cleanup")
    await rm(directory, { recursive: true, force: true })
  }
}

for (const phase of ["direct", "exploration", "planning"] as const) {
  test("meta review preserves its root planning phase: " + phase, async () => {
    await fixture(async workspace => {
      const before = O.snapshot("root")!
      const assigned = O.startChild({ parentSessionID: "root", sessionID: "review", subagentType: "meta-review" })
      expect(assigned.kind).toBe("meta_review")
      expect(assigned.claimIds).toEqual([])
      expect("workUnitId" in assigned ? assigned.workUnitId : undefined).toBeUndefined()
      expect(O.beginPrompt({ sessionID: "review", parentSessionID: "root", workspace, goal: "Review contract" }).instruction).toContain("Read-only")
      expect(await O.finishChild("review", true)).toBeUndefined()
      expect(await O.prepareCandidate("review")).toBeUndefined()
      const after = O.snapshot("root")!
      expect(after.phase).toBe(before.phase)
      expect(after.contractClaimIds).toEqual(before.contractClaimIds)
      expect(after.activeScopeIds).toEqual([])
      expect(after.completedScopeIds).toEqual(before.completedScopeIds)
      expect(after.candidates).toEqual([])
    }, phase)
  })
}

test("meta review only has four read-only tools and cannot create a candidate", async () => {
  await fixture(async workspace => {
    O.startChild({ parentSessionID: "root", sessionID: "review", subagentType: "meta-review" })
    for (const tool of ["read", "list", "glob", "grep"]) expect(() => O.assertToolAllowed("review", tool)).not.toThrow()
    for (const tool of ["bash", "argv", "shell", "write", "edit", "apply_patch", "task", "webfetch", "websearch", "harness_contract", "harness_workgraph", "harness_evidence", "harness_ready", "question", "skill", "lsp"]) {
      expect(() => O.assertToolAllowed("review", tool)).toThrow()
    }
    const route = await O.resolveRead("review", workspace, "input.txt")
    expect(route.overlay).toBe(false)
    expect(await readFile(route.physicalPath, "utf8")).toBe("unchanged")
    await expect(O.resolveWrite("review", workspace, "input.txt")).rejects.toMatchObject({ code: "OWNERSHIP_VIOLATION" })
    await expect(O.resolveRead("review", workspace, "../outside.txt")).rejects.toMatchObject({ code: "OWNERSHIP_VIOLATION" })
    await O.finishChild("review", false)
    expect(O.snapshot("root")!.phase).toBe("direct")
    expect(() => O.assertToolAllowed("review", "read")).toThrow()
    await expect(O.resolveRead("review", workspace, "input.txt")).rejects.toMatchObject({ code: "PHASE_VIOLATION" })
  })
})

test("meta review cannot reuse a scope, bind a WorkUnit or spawn a nested reviewer", async () => {
  await fixture(async () => {
    O.startChild({ parentSessionID: "root", sessionID: "review", subagentType: "meta-review" })
    for (const input of [
      { parentSessionID: "root", sessionID: "review", subagentType: "meta-review" },
      { parentSessionID: "review", sessionID: "nested", subagentType: "meta-review" },
      { parentSessionID: "root", sessionID: "worker-review", subagentType: "meta-review", workUnitId: "unit" },
    ]) expect(() => O.startChild(input)).toThrow()
    await O.finishChild("review", true)
    expect(() => O.startChild({ parentSessionID: "root", sessionID: "review", subagentType: "meta-review" })).toThrow()
  })
})
