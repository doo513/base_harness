import { expect, test } from "bun:test"
import { mkdtemp, mkdir, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import * as O from "../src/orchestration"

async function fixture(body: (workspace: string) => Promise<void>, exploration: "manual" | "always" = "manual") {
  const directory = await mkdtemp(join(tmpdir(), "harness-explicit-explore-"))
  const workspace = join(directory, "workspace")
  await mkdir(workspace)
  const keys = ["LOCALAPPDATA", "XDG_STATE_HOME"]
  const old = new Map(keys.map(key => [key, process.env[key]]))
  for (const key of keys) process.env[key] = join(directory, "state")
  const store = new O.WorkspaceCandidateStore()
  try {
    await O.withWorkspaceCandidateStore(store, async () => {
      O.beginPrompt({ sessionID: "root", workspace, goal: "Inspect input.txt", exploration })
      try { await body(workspace) } finally {
        try { await O.flushPersistence() } finally { store.clear() }
      }
    })
  } finally {
    for (const [key, value] of old) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    const rel = relative(tmpdir(), directory)
    if (!rel || rel.startsWith("..") || isAbsolute(rel)) throw new Error("Unsafe fixture cleanup")
    await rm(directory, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 })
  }
}

const start = (sessionID = "explorer") =>
  O.startChild({ parentSessionID: "root", sessionID, subagentType: "explore" })

for (const policy of ["manual", "always"] as const) {
  test("explicit discovery is read-only with policy " + policy, async () => {
    await fixture(async () => {
      expect(O.snapshot("root")!.phase).toBe(policy === "manual" ? "direct" : "exploration")
      const assigned = start()
      expect(assigned.kind).toBe("exploration")
      expect(assigned.claimIds).toEqual([])
      expect(O.snapshot("root")!.phase).toBe("exploration")
      expect(O.snapshot("root")!.explorationScopeId).toBe("explorer")
      expect(O.snapshot("root")!.activeScopeIds).toEqual(["explorer"])
      for (const tool of ["read", "list", "grep", "glob"]) {
        expect(() => O.assertToolAllowed("explorer", tool)).not.toThrow()
      }
      for (const tool of ["write", "edit", "apply_patch", "bash", "argv", "shell", "task", "webfetch", "harness_contract", "harness_ready"]) {
        expect(() => O.assertToolAllowed("explorer", tool)).toThrow()
      }
      expect(await O.prepareCandidate("explorer")).toBeUndefined()
      expect(O.snapshot("root")!.candidates).toEqual([])
      expect(O.hasContract("root")).toBe(false)
    }, policy)
  })
}

test("same running explorer is idempotent but a concurrent child is rejected", async () => {
  await fixture(async () => {
    const assigned = start()
    expect(start()).toEqual(assigned)
    expect(() => start("second")).toThrow()
    expect(O.snapshot("root")!.activeScopeIds).toEqual(["explorer"])
  })
})

for (const success of [true, false]) {
  test("finished exploration cannot restart: " + success, async () => {
    await fixture(async () => {
      start()
      await O.finishChild("explorer", success)
      expect(O.snapshot("root")!.phase).toBe(success ? "planning" : "blocked")
      expect(() => start()).toThrow()
      expect(() => start("second")).toThrow()
      expect(O.snapshot("root")!.activeScopeIds).toEqual([])
      expect(() => O.assertToolAllowed("explorer", "read")).toThrow()
    })
  })
}

test("accepted direct execution or planning cannot become fresh exploration", async () => {
  await fixture(async () => {
    O.registerContract("root", ["claim"], ["criterion"])
    O.beginDirectExecution("root")
    expect(() => start()).toThrow()
    O.beginPlanning("root")
    expect(() => start()).toThrow()
    expect(O.snapshot("root")!.explorationScopeId).toBeUndefined()
  })
})

test("returning to direct execution does not reset exploration identity", async () => {
  await fixture(async () => {
    start()
    await O.finishChild("explorer", true)
    O.registerContract("root", ["claim"], ["criterion"])
    O.beginDirectExecution("root")
    expect(() => start()).toThrow()
    expect(() => start("second")).toThrow()
    expect(O.snapshot("root")!.explorationScopeId).toBe("explorer")
  })
})

test("wrong parent, scope reuse, WorkUnit binding, and busy discovery are rejected", async () => {
  await fixture(async () => {
    expect(() => start("root")).toThrow()
    expect(() => O.startChild({ parentSessionID: "root", sessionID: "bound", subagentType: "explore", workUnitId: "unit" })).toThrow()
    O.startChild({ parentSessionID: "root", sessionID: "review", subagentType: "meta-review" })
    expect(() => O.startChild({ parentSessionID: "review", sessionID: "nested", subagentType: "explore" })).toThrow()
    expect(() => start("review")).toThrow()
    expect(() => start()).toThrow()
    await O.finishChild("review", true)
    expect(start().kind).toBe("exploration")
  })
})

for (const phase of ["ready", "blocked", "interrupted"] as const) {
  test("terminal root rejects exploration: " + phase, async () => {
    await fixture(async () => {
      if (phase === "interrupted") O.markInterrupted("root")
      else O.markOutcome("root", phase)
      expect(() => start()).toThrow()
      expect(O.snapshot("root")!.phase).toBe(phase)
      expect(O.snapshot("root")!.explorationScopeId).toBeUndefined()
    })
  })
}

test("a new run gets a fresh exploration identity, not a reused child", async () => {
  await fixture(async workspace => {
    start()
    O.markInterrupted("root")
    O.beginPrompt({ sessionID: "root", workspace, goal: "Inspect again", exploration: "manual" })
    expect(O.snapshot("root")!.explorationScopeId).toBeUndefined()
    expect(() => start()).toThrow()
    expect(start("new-explorer").kind).toBe("exploration")
  })
})
