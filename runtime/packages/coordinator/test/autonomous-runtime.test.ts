import { expect, test } from "bun:test"
import { mkdtemp, readFile, readdir, rm } from "node:fs/promises"
import { join } from "node:path"
import { tmpdir } from "node:os"
import type { DecisionAction, AutonomousRunSetup, AutonomousRunPorts } from "@base-harness/domain-contracts"
import { CoordinatorRuntime, RunRepository } from "../src"
import { writeAtomicSnapshot } from "@base-harness/workspace/snapshot-persistence"

const ref = (id: string) => ({ id, revision: 1, sha256: "a".repeat(64) })
async function fixture(persistent = false, deadlineMs = 60_000, configure?: (setup: AutonomousRunSetup, ports: AutonomousRunPorts) => void,
  repository?: RunRepository<any>) {
  const root = await mkdtemp(join(tmpdir(), "autonomous-runtime-"))
  let legacyStarts = 0
  let invokes = 0
  const runtime = new CoordinatorRuntime(async () => { legacyStarts++; throw new Error("legacy verifier must not start") }, {
    repository: repository ?? new RunRepository({ persistent, stateDirectory: join(root, "history") }),
  })
  const open = (sessionID: string) => runtime.openRun({ sessionID, workspace: root, goal: "Investigate", autonomousFactory: async (runId) => {
    const setup: AutonomousRunSetup = {
      binding: { schemaVersion: "autonomous-run-binding-v1", semantics: "autonomous-v1", runId, domainModule: ref("general"), executor: ref("fixture"), authorityRef: ref("grant"), budgetId: runId + ":budget" },
      taskId: sessionID,
      intent: { schemaVersion: "intent-v1", ref: ref("intent"), originalRequest: { ...ref("source"), kind: "source" }, requirements: [], constraints: [] },
      interpretation: { schemaVersion: "interpretation-v1", ref: ref("interpretation"), intentRef: ref("intent"), goalSummary: "Working hypothesis", assumptions: [], openQuestions: [], proposedCheckIds: [] },
      authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId, provenanceRefs: [{ sourceId: "user", sha256: "b".repeat(64) }], expiresAt: new Date(Date.now() + 60_000).toISOString(),
        capabilities: [{ operation: "read", targets: [{ kind: "workspace_path", selector: root }], exclusions: [] }] },
      limits: { deadlineAt: new Date(Date.now() + deadlineMs).toISOString(), maxActions: 20, maxParallelTasks: 1, maxTaskDepth: 0, maxTotalTasks: 1 },
      metering: { tokens: false, cost: false }, cleanupTimeoutMs: 1000, checks: [], gates: [], subjects: [{ ...ref("report"), kind: "report" }], gateEvidence: {},
    }
    const ports: AutonomousRunPorts = {
      resolveEffects: async () => [{ operation: "read", targets: [{ kind: "workspace_path", selector: join(root, "file") }] }],
      invoke: async () => { invokes++; return "read result" },
      measure: async () => { throw new Error("no registered check") }, authenticates: () => false,
      revise: ({ basedOnRef, ...value }) => ({ ...value, ref: { ...ref(basedOnRef.id), revision: basedOnRef.revision + 1 } }),
      cleanup: async () => [],
    }
    configure?.(setup, ports)
    return { setup, ports }
  } })
  const submit = (sessionID: string, runId: string, decisionId: string, action: DecisionAction) => runtime.submitAutonomousDecision(sessionID, runId, {
    schemaVersion: "decision-v1", decisionId, basis: runtime.autonomousBasis(sessionID, runId), observationIds: [], action,
  })
  return { root, runtime, open, submit, legacyStarts: () => legacyStarts, invokes: () => invokes,
    cleanup: async () => { await runtime.closeWorkspace(root); runtime.resetForTest(); await rm(root, { recursive: true, force: true }) } }
}
const read: DecisionAction = { kind: "invoke", toolId: "read", arguments: { path: "file" } }
const zero = { modelTokens: 0, costMinorUnits: 0 }
const finish: DecisionAction = { kind: "finish", report: { ...ref("report"), kind: "report" }, openWork: "drain",
  assessment: { status: "partial", summary: "Findings", citedObservationIds: [], uncertainties: [] } }

test("Coordinator owns the new lifecycle, dispatches only after Prepare, and never starts legacy verification", async () => {
  const f = await fixture()
  try {
    const opened = await f.open("session")
    expect(opened.phase).toBe("autonomous")
    expect(opened.autonomous?.lifecycle).toBe("preparing")
    expect((await f.submit("session", opened.runId, "early", read)).accepted).toBe(false)
    await f.runtime.prepareAutonomous("session", opened.runId, { status: "proceed", context: {} })
    expect(f.runtime.status("session").autonomous?.preparation).toEqual({
      basis: f.runtime.autonomousBasis("session", opened.runId), context: {},
    })
    expect((await f.submit("session", opened.runId, "read", read)).accepted).toBe(true)
    expect(f.invokes()).toBe(1)
    await expect(f.runtime.proposeContract("session", {} as never)).rejects.toThrow("SEMANTICS_FIXED")
    expect(() => f.runtime.beginDirect("session")).toThrow("SEMANTICS_FIXED")
    await f.runtime.verifyRoot("session")
    expect(f.legacyStarts()).toBe(0)
    expect(f.runtime.status("session").readyEligible).toBe(false)
    expect((await f.submit("session", opened.runId, "finish", finish)).accepted).toBe(true)
    expect(f.runtime.status("session").autonomous?.completion?.assessment?.status).toBe("partial")
  } finally { await f.cleanup() }
})

test("semantics stay fixed during a Run and old identities cannot dispatch after replacement", async () => {
  const f = await fixture()
  try {
    const old = await f.open("session")
    await expect(f.runtime.openRun({ sessionID: "session", workspace: f.root, goal: "legacy" })).rejects.toThrow("SEMANTICS_FIXED")
    await f.runtime.cancel("session")
    const fresh = await f.open("session")
    expect(fresh.runId).not.toBe(old.runId)
    await expect(f.runtime.submitAutonomousDecision("session", old.runId, {})).rejects.toThrow("RUN_MISMATCH")
    expect(f.invokes()).toBe(0)
    expect(f.runtime.status("session").autonomous?.budget.actions).toBe(0)
  } finally { await f.cleanup() }
})

test("simultaneous sessions retain distinct run bindings and model budget reservations", async () => {
  const f = await fixture()
  try {
    const [a, b] = await Promise.all([f.open("a"), f.open("b")])
    expect(a.runId).not.toBe(b.runId)
    const reservation = await f.runtime.reserveAutonomousModel("a", a.runId, "prepare", {}, { modelTokens: 0, costMinorUnits: 0 })
    expect(reservation.signal?.aborted).toBe(false)
    await f.runtime.settleAutonomousModel("a", a.runId, "prepare", { modelTokens: 0, costMinorUnits: 0 })
    expect(f.runtime.status("a").autonomous?.budget.actions).toBe(1)
    expect(f.runtime.status("b").autonomous?.budget.actions).toBe(0)
    await expect(f.runtime.prepareAutonomous("b", a.runId, { status: "proceed", context: {} })).rejects.toThrow("RUN_MISMATCH")
    await f.runtime.cancel("a")
    expect(f.runtime.status("b").autonomous?.lifecycle).toBe("preparing")
  } finally { await f.cleanup() }
})

test("cancelling a Run aborts its model lease and waits for owned settlement", async () => {
  const f = await fixture()
  try {
    const opened = await f.open("model-cancel")
    await f.runtime.prepareAutonomous("model-cancel", opened.runId, { status: "proceed", context: {} })
    const lease = await f.runtime.reserveAutonomousModel("model-cancel", opened.runId, "turn", {}, zero)
    const cancelling = f.runtime.cancel("model-cancel")
    await Promise.resolve()
    expect(lease.signal?.aborted).toBe(true)
    await f.runtime.settleAutonomousModel("model-cancel", opened.runId, "turn", { ...zero, complete: false })
    await cancelling
    expect(f.runtime.status("model-cancel").autonomous?.completion).toMatchObject({ reason: "cancelled", assessment: null })
    expect(f.runtime.status("model-cancel").autonomous?.budget.incompleteSettlementIds).toEqual(["model:turn"])
  } finally { await f.cleanup() }
})

test("v2 history keeps completion meaning and startup never restores execution", async () => {
  const f = await fixture(true)
  try {
    const done = await f.open("done")
    await f.runtime.prepareAutonomous("done", done.runId, { status: "proceed", context: {} })
    await f.submit("done", done.runId, "finish", finish)
    const interrupted = await f.open("interrupted")
    const history = join(f.root, "history")
    const completedBefore = JSON.parse(await readFile(join(history, done.runId + ".json"), "utf8"))
    expect(completedBefore.schemaVersion).toBe("coordinator-run-v2")
    expect(completedBefore).not.toHaveProperty("outcome")
    const restarted = new RunRepository({ persistent: true, stateDirectory: history })
    await restarted.initialize()
    expect(restarted.runs.size).toBe(0)
    expect(await readdir(history)).toHaveLength(2)
    const closed = JSON.parse(await readFile(join(history, done.runId + ".json"), "utf8"))
    expect(closed.autonomous.completion).toEqual(completedBefore.autonomous.completion)
    const stopped = JSON.parse(await readFile(join(history, interrupted.runId + ".json"), "utf8"))
    expect(stopped.autonomous.recovery).toEqual({ reason: "interrupted", processesResumed: false })
  } finally { await f.cleanup() }
})

test("an idle waiting Run publishes and persists deadline termination without another API call", async () => {
  const f = await fixture(true, 250)
  let off = () => {}
  let timeout: ReturnType<typeof setTimeout> | undefined
  try {
    const expired = new Promise<void>((resolve, reject) => {
      timeout = setTimeout(() => reject(new Error("deadline publication missing")), 2000)
      off = f.runtime.subscribe((status) => {
        if (status.autonomous?.completion?.reason === "deadline_exceeded") resolve()
      })
    })
    const opened = await f.open("waiting")
    await f.runtime.prepareAutonomous("waiting", opened.runId, { status: "needs_input", reason: "information", questions: ["Which file?"] })
    await expired
    const saved = JSON.parse(await readFile(join(f.root, "history", opened.runId + ".json"), "utf8"))
    expect(saved.autonomous.lifecycle).toBe("closed")
    expect(saved.autonomous.completion).toMatchObject({ reason: "deadline_exceeded", assessment: null })
    expect(f.invokes()).toBe(0)
    expect(f.legacyStarts()).toBe(0)
  } finally { off(); if (timeout) clearTimeout(timeout); await f.cleanup() }
})

test("a failed durable completion is reported as runtime_fault instead of requested success", async () => {
  const root = await mkdtemp(join(tmpdir(), "autonomous-persistence-fault-"))
  const repository = new RunRepository<any>({ persistent: true, stateDirectory: join(root, "history") }, async (target, body, options) => {
    const value = JSON.parse(body)
    if (value.autonomous?.lifecycle === "closed") throw Object.assign(new Error("completion sink failed"), { code: "FIXTURE_SINK_FAILED" })
    return writeAtomicSnapshot(target, body, options)
  })
  const f = await fixture(false, 60_000, undefined, repository)
  try {
    const opened = await f.open("persistence-fault")
    await f.runtime.prepareAutonomous("persistence-fault", opened.runId, { status: "proceed", context: {} })
    expect(await f.submit("persistence-fault", opened.runId, "finish", finish)).toEqual({ accepted: false, code: "STATUS_PERSISTENCE_FAILED" })
    expect(f.runtime.status("persistence-fault").autonomous?.completion).toMatchObject({
      reason: "runtime_fault", assessment: null,
    })
    expect(f.runtime.status("persistence-fault").autonomous?.completion?.unresolvedEffects)
      .toContain("Status persistence failed [FIXTURE_SINK_FAILED]")
    expect(f.runtime.status("persistence-fault")).toMatchObject({ phase: "blocked", outcome: "failure", failureKind: "harness_error" })
  } finally { await f.cleanup(); await rm(root, { recursive: true, force: true }) }
})

for (const failure of ["binding", "setup"] as const) test(`failed autonomous ${failure} initialization releases the transferred adapter`, async () => {
  let cleaned = 0
  const f = await fixture(false, 60_000, (setup, ports) => {
    if (failure === "binding") setup.binding.runId = "different-run"
    else setup.cleanupTimeoutMs = 0
    ports.cleanup = async () => { cleaned++; return [] }
  })
  try {
    await expect(f.open("invalid")).rejects.toThrow(failure === "binding" ? "HOST_BINDING" : "RUN_BINDING")
    expect(cleaned).toBe(1)
    expect(f.runtime.status("invalid").runId).toBe("")
  } finally { await f.cleanup() }
})

test("failed initialization does not wait forever for a transferred adapter that ignores cleanup", async () => {
  const f = await fixture(false, 60_000, (setup, ports) => {
    setup.binding.runId = "different-run"
    setup.cleanupTimeoutMs = 20
    ports.cleanup = () => new Promise<string[]>(() => undefined)
  })
  try {
    const started = Date.now()
    await expect(f.open("hung-cleanup")).rejects.toThrow("HOST_BINDING")
    expect(Date.now() - started).toBeLessThan(1000)
    expect(f.runtime.status("hung-cleanup").runId).toBe("")
  } finally { await f.cleanup() }
})
