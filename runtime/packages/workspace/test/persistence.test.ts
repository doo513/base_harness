import { expect, test } from "bun:test"
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, relative } from "node:path"
import * as Workspace from "../src/orchestration"

async function fixture(run: (value: {
  store: Workspace.WorkspaceCandidateStore
  directory: string
  start: (id: string) => void
  allowFailure: () => void
}) => Promise<void>) {
  const directory = await mkdtemp(join(tmpdir(), "harness-persistence-"))
  const workspace = join(directory, "workspace")
  const state = join(directory, "state")
  await mkdir(workspace)
  const store = new Workspace.WorkspaceCandidateStore()
  let expectedFailure = false
  const start = (id: string) => {
    const local = process.env.LOCALAPPDATA
    const xdg = process.env.XDG_STATE_HOME
    try {
      process.env.LOCALAPPDATA = state
      process.env.XDG_STATE_HOME = state
      Workspace.beginPrompt({ sessionID: id, workspace, goal: "Persist state", exploration: "manual" })
      Workspace.setRunIdentity(id, id + "-run")
    } finally {
      if (local === undefined) delete process.env.LOCALAPPDATA
      else process.env.LOCALAPPDATA = local
      if (xdg === undefined) delete process.env.XDG_STATE_HOME
      else process.env.XDG_STATE_HOME = xdg
    }
  }
  await Workspace.withWorkspaceCandidateStore(store, async () => {
    try {
      await run({ store, directory, start, allowFailure: () => { expectedFailure = true } })
    } finally {
      try {
        await store.flushPersistence().catch(error => { if (!expectedFailure) throw error })
      } finally {
        store.clear()
        expect(relative(tmpdir(), directory).startsWith("..")).toBe(false)
        await rm(directory, { recursive: true, force: true })
      }
    }
  })
}

test("workspace persistence drains ordered atomic snapshots with the actual run identity", async () => {
  await fixture(async ({ store, start }) => {
    start("root")
    for (let index = 0; index < 24; index++) Workspace.registerContract("root", ["claim-" + index], ["criterion"])
    Workspace.markInterrupted("root")
    await Workspace.flushPersistence("root")
    const root = store.roots.get("root")!
    const saved = JSON.parse(await readFile(join(root.stateDirectory, "orchestration.json"), "utf8"))
    expect(saved.runId).toBe("root-run")
    expect(saved.phase).toBe("interrupted")
    expect(saved.contractClaimIds).toEqual(["claim-23"])
    expect((await readdir(root.stateDirectory)).filter(name => name.endsWith(".tmp"))).toEqual([])
  })
})

test("a drained store can be cleared and removed without late writes", async () => {
  await fixture(async ({ store, start }) => {
    start("root")
    Workspace.markInterrupted("root")
    await store.flushPersistence()
    const root = store.roots.get("root")!
    expect(JSON.parse(await readFile(join(root.stateDirectory, "orchestration.json"), "utf8")).phase).toBe("interrupted")
    store.clear()
    await store.flushPersistence()
    expect(store.roots.size).toBe(0)
  })
})

test("state persistence failure is latched for its run without poisoning an independent run", async () => {
  await fixture(async ({ store, directory, start, allowFailure }) => {
    start("broken")
    await Workspace.flushPersistence("broken")
    const blocked = join(directory, "not-a-directory")
    await writeFile(blocked, "occupied")
    store.roots.get("broken")!.stateDirectory = blocked
    Workspace.registerContract("broken", ["claim"], ["criterion"])
    allowFailure()
    await expect(Workspace.flushPersistence("broken")).rejects.toMatchObject({ code: "PERSISTENCE_ERROR" })
    expect(() => Workspace.assertToolAllowed("broken", "write")).toThrow("persistence failed")
    start("independent")
    await Workspace.flushPersistence("independent")
    expect(() => Workspace.assertToolAllowed("independent", "write")).not.toThrow()
  })
})
