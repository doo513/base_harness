import { expect, test } from "bun:test"
import { promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"
import { writeAtomicSnapshot } from "../src/snapshot-persistence"
import { WorkspaceCandidateStore, OrchestrationError } from "../src/orchestration"

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

test("transient Windows rename errors retain old bytes until atomic replacement succeeds", async () => {
  const directory = await temporary()
  const target = path.join(directory, "snapshot.json")
  const old = '{"version":1}'
  const next = '{"version":2}'
  let attempts = 0
  const delays: number[] = []
  try {
    await fs.writeFile(target, old)
    const published = await writeAtomicSnapshot(target, next, {
      platform: "win32",
      sleep: async milliseconds => { delays.push(milliseconds) },
      rename: async (source, destination) => {
        expect(path.dirname(source)).toBe(path.dirname(destination))
        expect(await fs.readFile(destination, "utf8")).toBe(old)
        if (++attempts < 3) throw Object.assign(new Error("sharing conflict"), { code: "EPERM" })
        await fs.rename(source, destination)
      },
    })
    expect(published).toBe(true)
    expect(attempts).toBe(3)
    expect(delays).toEqual([10, 25])
    expect(await fs.readFile(target, "utf8")).toBe(next)
    expect(await fs.readdir(directory)).toEqual(["snapshot.json"])
  } finally { await cleanup(directory) }
})

test("permanent Windows failure is bounded and never removes the previous snapshot", async () => {
  const directory = await temporary()
  const target = path.join(directory, "snapshot.json")
  let attempts = 0
  const delays: number[] = []
  const failure = Object.assign(new Error("still locked"), { code: "EPERM" })
  try {
    await fs.writeFile(target, "old")
    await expect(writeAtomicSnapshot(target, "new", {
      platform: "win32",
      sleep: async milliseconds => { delays.push(milliseconds) },
      rename: async () => { attempts++; throw failure },
    })).rejects.toThrow("still locked")
    expect(attempts).toBe(6)
    expect(delays).toEqual([10, 25, 50, 100, 200])
    expect(await fs.readFile(target, "utf8")).toBe("old")
    expect(await fs.readdir(directory)).toEqual(["snapshot.json"])
  } finally { await cleanup(directory) }
})

for (const [platform, code] of [["linux", "EPERM"], ["win32", "ENOSPC"]] as const) {
  test("non-retryable platform/code fails without backoff: " + platform + "/" + code, async () => {
    const directory = await temporary()
    let attempts = 0
    let slept = false
    try {
      await expect(writeAtomicSnapshot(path.join(directory, "snapshot.json"), "new", {
        platform,
        sleep: async () => { slept = true },
        rename: async () => { attempts++; throw Object.assign(new Error(code), { code }) },
      })).rejects.toThrow(code)
      expect(attempts).toBe(1)
      expect(slept).toBe(false)
      expect(await fs.readdir(directory)).toEqual([])
    } finally { await cleanup(directory) }
  })
}

test("generation invalidation during backoff prevents late publication", async () => {
  const directory = await temporary()
  const target = path.join(directory, "snapshot.json")
  let current = true
  let attempts = 0
  try {
    await fs.writeFile(target, "old")
    expect(await writeAtomicSnapshot(target, "stale", {
      platform: "win32",
      isCurrent: () => current,
      sleep: async () => { current = false },
      rename: async () => { attempts++; throw Object.assign(new Error("locked"), { code: "EBUSY" }) },
    })).toBe(false)
    expect(attempts).toBe(1)
    expect(await fs.readFile(target, "utf8")).toBe("old")
    expect(await fs.readdir(directory)).toEqual(["snapshot.json"])
  } finally { await cleanup(directory) }
})

test("a failed workspace root remains failed while another root can persist", async () => {
  const directory = await temporary()
  let badWrites = 0
  const store = new WorkspaceCandidateStore(async (target, body, options) => {
    if (path.basename(path.dirname(target)) === "bad") {
      badWrites++
      throw Object.assign(new Error("fixture persistence failure"), { code: "EPERM" })
    }
    return writeAtomicSnapshot(target, body, options)
  })
  const root = (id: string) => ({
    sessionID: id, runId: id, workspace: directory, goal: "fixture",
    phase: "planning" as const, exploration: "manual" as const, maxParallelWorkUnits: 2,
    contractClaimIds: new Set<string>(), contractCriterionIds: new Set<string>(),
    active: new Set<string>(), completed: new Set<string>(), stateDirectory: path.join(directory, id),
  })
  const bad = root("bad"), good = root("good")
  try {
    store.enqueuePersistence(bad, "bad")
    await expect(store.flushPersistence(bad)).rejects.toBeInstanceOf(OrchestrationError)
    store.enqueuePersistence(bad, "must-not-recover-silently")
    store.enqueuePersistence(good, "good")
    await store.flushPersistence(good)
    await expect(store.flushPersistence(bad)).rejects.toThrow("Workspace state persistence failed")
    expect(badWrites).toBe(1)
    expect(await fs.readFile(path.join(good.stateDirectory, "orchestration.json"), "utf8")).toBe("good")
  } finally { await store.flushPersistence().catch(() => undefined); await cleanup(directory) }
})
