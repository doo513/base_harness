import { afterEach, beforeEach, expect, test } from "bun:test"
import { mkdtemp, mkdir, readFile, realpath, rm, unlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { KernelHost } from "../src"
import { SessionStateStore, summarizeRun, sessionSelection } from "../src/session-state-store"
import { createKernelSessionState } from "@base-harness/kernel"

let directory: string
let workspace: string
beforeEach(async () => {
  directory = await mkdtemp(path.join(os.tmpdir(), "base-harness-history-test-"))
  workspace = path.join(directory, "workspace")
  await mkdir(workspace)
})
afterEach(async () => {
  const parent = await realpath(os.tmpdir())
  const actual = await realpath(directory)
  if (path.dirname(actual) !== parent || !path.basename(actual).startsWith("base-harness-history-test-")) {
    throw new Error("Unsafe scratch cleanup")
  }
  await rm(actual, { recursive: true, force: true })
})

const selection = () => sessionSelection(createKernelSessionState())
const location = () => path.join(directory, "history")
const inactive = (sessionID = "session") => ({
  sessionID, workspace: "", runId: "", goal: "", phase: "inactive", workers: [],
  activeCount: 0, queuedCount: 0, readyEligible: false, verificationState: "inactive",
  evidenceCount: 0, candidateCount: 0, evidenceRefs: [], candidateRefs: [], repairCount: 0,
})
const runtimeFixture = () => {
  let current: any = inactive()
  let calls = 0
  const runtime = {
    status: () => current,
    openRun: async (input: any) => {
      calls += 1
      return current = { ...inactive(input.sessionID), ...input, runId: "new-run", phase: "planning" }
    },
    proposeContract: async () => { throw new Error("Unexpected verifier call") },
    acceptWorkGraph: async () => { throw new Error("Unexpected worker call") },
  }
  return { runtime, calls: () => calls, set: (status: any) => { current = status } }
}
const host = (runtime: ReturnType<typeof runtimeFixture>["runtime"]) =>
  new KernelHost(runtime, { directory: path.join(directory, "plans"), sessionState: { directory: location() } })
const terminalStatus = (phase = "ready") => ({
  ...inactive(), workspace, runId: "old-run", goal: "completed fixture task", phase,
  planningState: "executing", outcome: phase, readyEligible: phase === "ready",
  workers: [{ workUnitId: "unit", title: "fixture unit", state: "completed", repairCount: 0 }],
  evidenceCount: 2, evidenceRefs: ["artifact-a", "artifact-b"], assuranceLevel: "adaptive",
})

test("domain, skill and plan-once controls survive a cold Host without opening any run", async () => {
  const first = runtimeFixture(), a = host(first.runtime)
  await a.control("session", { type: "skill.set", skill: "hackathon", enabled: true }, undefined, workspace)
  await a.control("session", { type: "planning.plan_once" }, undefined, workspace)
  const second = runtimeFixture(), b = host(second.runtime)
  const status = await b.readStatus("session", workspace)
  expect(status.domain).toBe("develop")
  expect(status.skills).toEqual(["hackathon"])
  expect(status.planningPreference).toBe("plan_once")
  expect(status.planningState).toBe("idle")
  expect(status.runId).toBe("")
  expect(status.readyEligible).toBe(false)
  expect(first.calls() + second.calls()).toBe(0)
})

for (const phase of ["ready", "blocked", "failure", "interrupted", "worker_running", "direct"]) {
  test("cold history is read-only, never current authority: " + phase, async () => {
    const first = runtimeFixture(), a = host(first.runtime)
    await a.control("session", { type: "domain.set", domain: "general" }, undefined, workspace)
    await a.checkpointStatus(terminalStatus(phase))
    await writeFile(path.join(workspace, "changed-after-run.txt"), "different workspace contents")
    const second = runtimeFixture(), b = host(second.runtime)
    const events: unknown[] = []
    b.subscribe(status => { events.push(status) })
    const status = await b.readStatus("session", workspace)
    expect(status.phase).toBe("inactive")
    expect(status.runId).toBe("")
    expect(status.readyEligible).toBe(false)
    expect(status.evidenceRefs).toEqual([])
    expect(status.activePlanId).toBeUndefined()
    expect(status.goalContract).toBeUndefined()
    expect(status.history.runId).toBe("old-run")
    expect(status.history.phase).toBe(["direct", "worker_running"].includes(phase) ? "interrupted" : phase)
    expect(status.history.readOnly).toBe(true)
    expect(status.history.revalidated).toBe(false)
    expect(status.history.evidenceCount).toBe(2)
    expect(status.history.workers).toHaveLength(1)
    expect(status.domain).toBe("general")
    expect(events).toEqual([])
    expect(second.calls()).toBe(0)
    await expect(b.control("session", { type: "planning.execute", planId: "old-plan" })).rejects.toThrow("PLAN_NOT_READY")
    expect(() => b.assertToolAllowed("session", "edit")).toThrow()
  })
}

test("a new request keeps the saved domain but starts a new run, without old history authority", async () => {
  const first = runtimeFixture(), a = host(first.runtime)
  await a.control("session", { type: "domain.set", domain: "general" }, undefined, workspace)
  await a.checkpointStatus(terminalStatus())
  const next = runtimeFixture(), b = host(next.runtime)
  const status = await b.openRun({ sessionID: "session", workspace, goal: "new request", defaultDomain: "develop" })
  expect(status.domain).toBe("general")
  expect(status.runId).toBe("new-run")
  expect(status.history).toBeUndefined()
  expect(status.readyEligible).toBe(false)
  expect(next.calls()).toBe(1)
})

test("signed identity cannot be loaded into another workspace", async () => {
  const store = new SessionStateStore({ directory: location() })
  await store.save({ sessionID: "session", workspace, selection: selection() })
  const other = path.join(directory, "other")
  await mkdir(other)
  await expect(store.load("session", other)).rejects.toThrow("SESSION_WORKSPACE_MISMATCH")
})

test("tampering cannot promote selection or saved history", async () => {
  const store = new SessionStateStore({ directory: location() })
  await store.save({ sessionID: "session", workspace, selection: selection(), lastRun: summarizeRun(terminalStatus()) })
  const file = path.join(location(), "session.json")
  const envelope = JSON.parse(await readFile(file, "utf8"))
  envelope.body.selection.domain = "general"
  await writeFile(file, JSON.stringify(envelope))
  await expect(new SessionStateStore({ directory: location() }).load("session", workspace))
    .rejects.toThrow("SESSION_INTEGRITY_INVALID")
})

test("missing signing key does not become an empty/default session", async () => {
  const store = new SessionStateStore({ directory: location() })
  await store.save({ sessionID: "session", workspace, selection: selection() })
  await unlink(path.join(location(), ".signing-key"))
  await expect(store.load("session", workspace)).rejects.toThrow("SESSION_STORE_KEY_INVALID")
})

test("Host state cannot be stored inside an actor workspace", async () => {
  const store = new SessionStateStore({ directory: path.join(workspace, "state") })
  await expect(store.save({ sessionID: "session", workspace, selection: selection() }))
    .rejects.toThrow("SESSION_STORE_PATH_INVALID")
})

test("redaction affects persisted history but cannot silently alter a selection", async () => {
  const secret = "fixture-private-value"
  const store = new SessionStateStore({
    directory: location(),
    redact: <T>(_run: string, value: T): T => JSON.parse(JSON.stringify(value).replaceAll(secret, "[REDACTED]")),
  })
  await store.save({ sessionID: "session", workspace, selection: selection(),
    lastRun: summarizeRun({ ...terminalStatus(), goal: secret }) })
  expect((await store.load("session", workspace))!.lastRun!.goal).toBe("[REDACTED]")
  expect(await readFile(path.join(location(), "session.json"), "utf8")).not.toContain(secret)
  await expect(store.save({ sessionID: "session", workspace,
    selection: { ...selection(), execution: { adapterID: "fixture", options: { token: secret } } } }))
    .rejects.toThrow("SESSION_REDACTION_INVALID")
})

test("failed atomic replacement keeps the previous signed selection", async () => {
  const store = new SessionStateStore({ directory: location() })
  await store.save({ sessionID: "session", workspace, selection: selection() })
  const failing = new SessionStateStore({ directory: location() }, async () => false)
  await expect(failing.save({ sessionID: "session", workspace, selection: { ...selection(), domain: "general" } }))
    .rejects.toThrow("SESSION_STORE_WRITE_INVALIDATED")
  expect((await store.load("session", workspace))!.selection.domain).toBe("develop")
})

test("concurrent controls serialize instead of losing a previously selected skill", async () => {
  const fixture = runtimeFixture(), instance = host(fixture.runtime)
  await Promise.all([
    instance.control("session", { type: "skill.set", skill: "hackathon", enabled: true }, undefined, workspace),
    instance.control("session", { type: "planning.plan_once" }, undefined, workspace),
  ])
  const saved = await host(runtimeFixture().runtime).readStatus("session", workspace)
  expect(saved.skills).toEqual(["hackathon"])
  expect(saved.planningPreference).toBe("plan_once")
})
