import { afterEach, beforeEach, expect, test } from "bun:test"
import { mkdtemp, mkdir, realpath, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { CoordinatorRuntime } from "../src"

let directory: string
let workspace: string
let runtime: CoordinatorRuntime
let oldLocal: string | undefined, oldState: string | undefined
beforeEach(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), "base-harness-checkpoint-test-"))
  workspace = path.join(directory, "workspace")
  await mkdir(workspace)
  oldLocal = process.env.LOCALAPPDATA
  oldState = process.env.XDG_STATE_HOME
  process.env.LOCALAPPDATA = directory
  process.env.XDG_STATE_HOME = directory
  runtime = new CoordinatorRuntime((async () => { throw new Error("Verifier must not start in checkpoint fixture") }) as any)
})
afterEach(async () => {
  await runtime.orchestration.flushPersistence("checkpoint").catch(() => undefined)
  runtime.resetForTest()
  if (oldLocal === undefined) delete process.env.LOCALAPPDATA
  else process.env.LOCALAPPDATA = oldLocal
  if (oldState === undefined) delete process.env.XDG_STATE_HOME
  else process.env.XDG_STATE_HOME = oldState
  const actual = await realpath(directory), parent = await realpath(os.tmpdir())
  if (path.dirname(actual) !== parent || !path.basename(actual).startsWith("base-harness-checkpoint-test-")) {
    throw new Error("Unsafe scratch cleanup")
  }
  await rm(actual, { recursive: true, force: true })
})

test("initial status is not published before the durable Host checkpoint settles", async () => {
  let release!: () => void, entered!: () => void
  const barrier = new Promise<void>(resolve => { release = resolve })
  const started = new Promise<void>(resolve => { entered = resolve })
  const events: unknown[] = []
  runtime.registerStatusCheckpoint(async () => { entered(); await barrier })
  runtime.subscribe(status => { events.push(status) })
  const opening = runtime.openRun({ sessionID: "checkpoint", workspace, goal: "fixture task" })
  await started
  expect(events).toHaveLength(0)
  release()
  const status = await opening
  expect(events).toHaveLength(1)
  expect(status.runId).toBeTruthy()
  expect(status.readyEligible).toBe(false)
})

test("checkpoint failure is latched as a Host failure, not a repairable implementation result", async () => {
  runtime.registerStatusCheckpoint(async () => { throw new Error("fixture storage failure") })
  const events: any[] = []
  runtime.subscribe(status => { events.push(status) })
  const status = await runtime.openRun({ sessionID: "checkpoint", workspace, goal: "fixture task" })
  expect(status.phase).toBe("blocked")
  expect(status.failureKind).toBe("harness_error")
  expect(status.readyEligible).toBe(false)
  expect(events.some(event => event.outcome === "ready")).toBe(false)
  const verified = await runtime.verifyRoot("checkpoint", "completion")
  expect(verified.readyEligible).toBe(false)
  expect(verified.failureKind).toBe("harness_error")
})

test("synthetic Ready publication waits for checkpoint and cannot escape a failed sink", async () => {
  await runtime.openRun({ sessionID: "checkpoint", workspace, goal: "fixture task" })
  // White-box publication fixture only; it is not a verifier acceptance or a Harness Evidence artifact.
  const internal = runtime as any
  const run = internal.runFor("checkpoint")
  run.verification = { ...run.verification, state: "ready", outcome: "ready", readyEligible: true }
  runtime.orchestration.markOutcome("checkpoint", "ready")
  let release!: () => void, entered!: () => void
  const barrier = new Promise<void>(resolve => { release = resolve })
  const started = new Promise<void>(resolve => { entered = resolve })
  runtime.registerStatusCheckpoint(async status => {
    if (status.outcome !== "ready") return
    entered()
    await barrier
    throw new Error("fixture storage failure")
  })
  const events: any[] = []
  runtime.subscribe(status => { events.push(status) })
  const publishing = internal.publish(run)
  await started
  expect(events).toHaveLength(0)
  release()
  await publishing
  expect(events.some(event => event.outcome === "ready")).toBe(false)
  expect(runtime.status("checkpoint").readyEligible).toBe(false)
  expect(runtime.status("checkpoint").failureKind).toBe("harness_error")
})
