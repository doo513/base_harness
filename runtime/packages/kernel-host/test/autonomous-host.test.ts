import { expect, test } from "bun:test"
import { mkdtemp, readFile, rm, writeFile, readdir } from "node:fs/promises"
import { join } from "node:path"
import { tmpdir } from "node:os"
import { builtinAutonomousDomainModules } from "@base-harness/domain"
import type { AutonomousDomainModule, Json, SubjectRef } from "@base-harness/domain-contracts"
import { CoordinatorRuntime, RunRepository } from "../../coordinator/src"
import { KernelHost, type AutonomousHostOptions } from "../src"

async function fixture(modules: readonly AutonomousDomainModule[] = builtinAutonomousDomainModules, overrides: Partial<AutonomousHostOptions> = {}) {
  const root = await mkdtemp(join(tmpdir(), "autonomous-host-"))
  await writeFile(join(root, "source.txt"), "actual source")
  const runtime = new CoordinatorRuntime(async () => { throw new Error("legacy verifier forbidden") }, {
    repository: new RunRepository({ persistent: false }),
  })
  let authorizations = 0
  const options: AutonomousHostOptions = {
    modules, artifactDirectory: join(root, "artifacts"), cleanupTimeoutMs: 2000,
    metering: { tokens: false, cost: false },
    limits: () => ({ deadlineAt: new Date(Date.now() + 60_000).toISOString(), maxActions: 20, maxParallelTasks: 1, maxTaskDepth: 0, maxTotalTasks: 1 }),
    authorize: async () => {
      authorizations++
      return { capabilities: [{ operation: "read", targets: [{ kind: "workspace_path", selector: root }], exclusions: [] }],
        provenanceRefs: [{ sourceId: "test-user-permission", sha256: "a".repeat(64) }], expiresAt: new Date(Date.now() + 60_000).toISOString() }
    },
    adapter: async (input) => {
      const measurement = runtime.createAutonomousMeasurementPorts({ runId: input.runId, snapshotRoot: input.snapshotRoot,
        subject: input.subject, check: input.check, environmentHash: "b".repeat(64) })
      return {
        ...measurement,
        resolveEffects: async (action) => [{ operation: "read", targets: [{ kind: "workspace_path", selector:
          action.kind === "measure" ? input.subject(action.subject).origin ?? root : join(root, "source.txt") }] }],
        invoke: async (proposal) => {
          if (proposal.action.kind !== "invoke") throw new Error("wrong action")
          host.assertToolAllowed(input.sessionID, proposal.action.toolId)
          const bytes = await readFile(join(root, "source.txt"))
          const stored = await host.captureAutonomousSource(input.sessionID, input.runId, bytes, join(root, "source.txt"))
          return JSON.parse(JSON.stringify({ text: bytes.toString(), subject: stored.subject })) as Json
        },
        describeCheck: (parameters, stored) => {
          const manifest = JSON.parse(stored.manifestJson)
          return { executorId: "python-measurement", supportedSubjects: [stored.subject.kind], timeoutMs: 5000, requiredCapabilities: ["read"],
            parameters: { kind: "file", path: manifest.files[0].path, operator: "equals", expected: (parameters as { expected: string }).expected } }
        },
      }
    },
  }
  Object.assign(options, overrides)
  const host = new KernelHost(runtime, { autonomous: options, directory: join(root, "plans") })
  const open = (sessionID = "session", goal = "Read source.txt and explain it", context?: unknown) => host.openRun({ sessionID, workspace: root, goal, context, defaultDomain: "general", semantics: "autonomous-v1",
    domainExecutor: { id: "fixture-model", revision: "model-r1", kind: "model_api", providerId: "fixture", modelId: "local", options: {} } })
  return { root, runtime, host, open, authorizations: () => authorizations,
    cleanup: async () => { await runtime.closeWorkspace(root); runtime.resetForTest(); await rm(root, { recursive: true, force: true }) } }
}

test("Host -> Coordinator -> admitted read -> real Python observation -> partial finish uses one Run", async () => {
  const f = await fixture()
  try {
    const opened = await f.open()
    expect(opened.autonomous.lifecycle).toBe("active")
    expect(opened.autonomous.intent.requirements[0].text).toBe("Read source.txt and explain it")
    expect(f.authorizations()).toBe(1)
    expect(() => f.host.assertToolAllowed("session", "read")).toThrow("ADMISSION_REQUIRED")
    await expect(f.host.captureAutonomousSource("session", opened.runId, Buffer.from("bypass"), join(f.root, "source.txt")))
      .rejects.toThrow("ADMISSION_REQUIRED")
    const read = await f.host.submitAutonomousDecision("session", opened.runId, "read", { kind: "invoke", toolId: "read", arguments: { filePath: join(f.root, "source.txt") } })
    expect(read.accepted).toBe(true)
    if (!read.accepted) throw new Error("read not admitted")
    const subject = (read.output as unknown as { subject: SubjectRef }).subject
    const check = f.host.proposeAutonomousCheck("session", opened.runId, subject, { expected: "deliberately different", author: "application" })
    expect(check.author).toBe("model")
    const measured = await f.host.submitAutonomousDecision("session", opened.runId, "measure", { kind: "measure", subject, checkRef: check.ref })
    if (!measured.accepted) throw new Error(measured.code)
    expect(measured.accepted).toBe(true)
    expect(f.runtime.status("session").autonomous?.observations[0]?.result).toMatchObject({ execution: "completed",
      findings: [{ name: "sha256" }, { name: "size" }, { name: "file_content", result: "fail" }] })
    expect(f.runtime.status("session").autonomous?.lifecycle).toBe("active")
    expect((await f.host.submitAutonomousDecision("session", opened.runId, "reinvestigate", { kind: "invoke", toolId: "read", arguments: {} })).accepted).toBe(true)
    const done = await f.host.submitAutonomousDecision("session", opened.runId, "final", {
      kind: "final", text: "The source says 'actual source'. The selected comparison failed; its expectation may need review.", openWork: "drain",
      assessment: { status: "partial", summary: "The selected comparison failed", uncertainties: ["Whether the test expectation is appropriate"],
        citedObservationIds: f.runtime.status("session").autonomous!.observations.map((o) => o.observationId) },
    })
    expect(done.accepted).toBe(true)
    expect(f.runtime.status("session").autonomous?.completion).toMatchObject({ reason: "requested", assessment: { status: "partial" } })
    expect(f.runtime.status("session").readyEligible).toBe(false)
    expect(await readFile(join(f.root, "source.txt"), "utf8")).toBe("actual source")
  } finally { await f.cleanup() }
})

test("same plain-text final is stored once even when submitted concurrently", async () => {
  const f = await fixture()
  try {
    const opened = await f.open()
    const outcomes = await Promise.all([f.host.submitAutonomousDecision("session", opened.runId, "final", "Ready and successful!"),
      f.host.submitAutonomousDecision("session", opened.runId, "final", "Ready and successful!")])
    expect(outcomes[0]).toEqual(outcomes[1])
    expect(outcomes[0].accepted).toBe(true)
    const [directory] = await readdir(join(f.root, "artifacts"))
    expect(await readdir(join(f.root, "artifacts", directory!))).toHaveLength(4) // request + two binding snapshots + final
    expect(f.runtime.status("session").autonomous?.completion?.assessment?.status).toBe("not_assessed")
    expect(await f.host.submitAutonomousDecision("session", opened.runId, "final", "different")).toEqual({ accepted: false, code: "AUTONOMOUS_REQUEST_CONFLICT" })
  } finally { await f.cleanup() }
})

test("actor cannot replace grant or basis; detached snapshots cannot modify runtime authority", async () => {
  const f = await fixture()
  try {
    const opened = await f.open()
    const response = { kind: "invoke", toolId: "read", arguments: {}, authorityGrant: { unrestricted: true } }
    expect((await f.host.submitAutonomousDecision("session", opened.runId, "forged", response)).accepted).toBe(false)
    const basis = f.runtime.autonomousBasis("session", opened.runId)
    expect((await f.host.submitAutonomousDecision("session", opened.runId, "stale", { schemaVersion: "decision-v1", decisionId: "stale",
      basis: { ...basis, runId: "other" }, observationIds: [], action: { kind: "invoke", toolId: "read", arguments: {} } })).accepted).toBe(false)
    opened.autonomous.authority.capabilities[0].operation = "mutate"
    expect(f.runtime.status("session").autonomous?.authority.capabilities[0]?.operation).toBe("read")
  } finally { await f.cleanup() }
})

test("a deferred final keeps its captured basis and is rejected after interpretation changes", async () => {
  const f = await fixture()
  try {
    const opened = await f.open()
    const [artifactDirectory] = await readdir(join(f.root, "artifacts"))
    const before = await readdir(join(f.root, "artifacts", artifactDirectory!))
    const staleBasis = f.runtime.autonomousBasis("session", opened.runId)
    const revised = await f.host.submitAutonomousDecision("session", opened.runId, "revise", {
      kind: "revise_interpretation", proposal: {
        schemaVersion: "interpretation-v1", basedOnRef: staleBasis.interpretationRef, intentRef: staleBasis.intentRef,
        goalSummary: "A revised explanation", assumptions: [], openQuestions: [], proposedCheckIds: [],
      },
    })
    expect(revised.accepted).toBe(true)
    const result = await f.host.submitAutonomousDecision("session", opened.runId, "deferred-final", {
      kind: "final", text: "Outdated conclusion", basedOn: staleBasis, openWork: "drain",
      assessment: { status: "partial", summary: "Outdated", uncertainties: [], citedObservationIds: [] },
    })
    expect(result).toEqual({ accepted: false, code: "AUTONOMOUS_STALE_BASIS" })
    expect(await readdir(join(f.root, "artifacts", artifactDirectory!))).toEqual(before)
    expect(f.runtime.status("session").autonomous?.lifecycle).toBe("active")
  } finally { await f.cleanup() }
})

test("replaceable Prepare may pause for missing input without starting execution", async () => {
  const base = builtinAutonomousDomainModules[0]!
  const f = await fixture([{ ...base, prepare: () => ({ status: "needs_input", reason: "information", questions: ["Which revision?"] }) }])
  try {
    const opened = await f.open()
    expect(opened.autonomous.lifecycle).toBe("waiting_input")
    expect((await f.host.submitAutonomousDecision("session", opened.runId, "read", { kind: "invoke", toolId: "read", arguments: {} })).accepted).toBe(false)
    expect(opened.autonomous.budget.actions).toBe(0)
  } finally { await f.cleanup() }
})

test("replaceable decision strategies receive detached immutable candidate data", async () => {
  const base = builtinAutonomousDomainModules[0]!
  let frozenInput = false
  const f = await fixture([{ ...base, normalizeDecision: (input) => {
    frozenInput = Object.isFrozen(input) && Object.isFrozen(input.response)
    return structuredClone(input.response)
  } }])
  try {
    const opened = await f.open()
    const candidate = { kind: "ask", reason: "information", questions: ["Which revision?"] }
    expect((await f.host.submitAutonomousDecision("session", opened.runId, "ask", candidate)).accepted).toBe(true)
    expect(frozenInput).toBe(true)
    expect(candidate).toEqual({ kind: "ask", reason: "information", questions: ["Which revision?"] })
  } finally { await f.cleanup() }
})

test("plan-only cannot silently start autonomous execution, and an unregistered domain fails explicitly", async () => {
  const f = await fixture([])
  try {
    await expect(f.host.openRun({ sessionID: "plan", workspace: f.root, goal: "Plan", semantics: "autonomous-v1", planOnly: true })).rejects.toThrow("PLAN_EXECUTION_UNSUPPORTED")
    expect(f.authorizations()).toBe(0)
    await expect(f.open()).rejects.toThrow("UNREGISTERED")
    expect(f.runtime.status("session").runId).toBe("")
  } finally { await f.cleanup() }
})

test("authenticated answers revise sourced intent once while preserving authority and accumulated budget", async () => {
  let calls = 0
  const base = builtinAutonomousDomainModules[0]!
  const f = await fixture([{ ...base, prepare: (input) => input.intent.requirements.length === 1
    ? { status: "needs_input", reason: "information", questions: ["Which revision?"] }
    : { status: "proceed", context: {} } }], { ask: async () => { calls++; return [["revision 7"]] } })
  try {
    const opened = await f.open()
    const before = opened.autonomous
    const prepared = await Promise.all([f.host.requestAutonomousAnswers("session", opened.runId), f.host.requestAutonomousAnswers("session", opened.runId)])
    expect(prepared.map((item) => item.status)).toEqual(["proceed", "proceed"])
    expect(calls).toBe(1)
    const after = f.runtime.status("session").autonomous!
    expect(after.intent.ref.revision).toBe(before.intent.ref.revision + 1)
    expect(after.intent.originalRequest).toEqual(before.intent.originalRequest)
    expect(after.intent.requirements[1]!.text).toContain("revision 7")
    expect(after.intent.requirements[1]!.sourceRefs[0]!.sourceId).toStartWith("source:")
    expect(after.authority).toEqual(before.authority)
    expect(after.budget).toEqual(before.budget)
    expect(after.lifecycle).toBe("active")
    expect(() => f.host.reserveAutonomousModel("session", opened.runId, "wrong-model", { providerId: "other", modelId: "local" }, { modelTokens: 0, costMinorUnits: 0 })).toThrow("EXECUTOR_BINDING")
    await f.host.reserveAutonomousModel("session", opened.runId, "model", { providerId: "fixture", modelId: "local" }, { modelTokens: 0, costMinorUnits: 0 })
    await f.host.settleAutonomousModel("session", opened.runId, "model", { modelTokens: 0, costMinorUnits: 0 })
    await f.host.submitAutonomousDecision("session", opened.runId, "permission-question", { kind: "ask", reason: "authority", questions: ["May I write?"] })
    await f.host.requestAutonomousAnswers("session", opened.runId)
    expect(f.runtime.status("session").autonomous!.authority).toEqual(before.authority)
    expect(f.runtime.status("session").autonomous!.budget.actions).toBe(1)
  } finally { await f.cleanup() }
})

test("a later user message revises active intent in the same Run without resetting authority or budget", async () => {
  const f = await fixture()
  try {
    const opened = await f.open("session", "Read source.txt", { messageID: "user-1" })
    await f.host.reserveAutonomousModel("session", opened.runId, "model", { providerId: "fixture", modelId: "local" }, { modelTokens: 0, costMinorUnits: 0 })
    await f.host.settleAutonomousModel("session", opened.runId, "model", { modelTokens: 9, costMinorUnits: 0 })
    const revised = await f.open("session", "Also explain any uncertainty", { messageID: "user-2" })
    expect(revised.runId).toBe(opened.runId)
    expect(revised.autonomous.intent.ref.revision).toBe(2)
    expect(revised.autonomous.intent.originalRequest).toEqual(opened.autonomous.intent.originalRequest)
    expect(revised.autonomous.intent.requirements.map((item: { text: string }) => item.text)).toEqual([
      "Read source.txt", "Also explain any uncertainty",
    ])
    expect(revised.autonomous.interpretation.intentRef).toEqual(revised.autonomous.intent.ref)
    expect(revised.autonomous.authority).toEqual(opened.autonomous.authority)
    expect(revised.autonomous.budget.actions).toBe(1)
    expect(revised.autonomous.budget.used.modelTokens).toBe(9)
    const replay = await f.open("session", "Also explain any uncertainty", { messageID: "user-2" })
    expect(replay.autonomous.intent.requirements).toHaveLength(2)
  } finally { await f.cleanup() }
})

test("question rejection and malformed answers leave the Run waiting without revising intent", async () => {
  let reject = true
  const f = await fixture(undefined, { ask: async () => { if (reject) throw new Error("QUESTION_REJECTED"); return [[]] } })
  try {
    const opened = await f.open()
    await f.host.submitAutonomousDecision("session", opened.runId, "ask", { kind: "ask", reason: "information", questions: ["Which file?"] })
    await expect(f.host.requestAutonomousAnswers("session", opened.runId)).rejects.toThrow("QUESTION_REJECTED")
    reject = false
    await expect(f.host.requestAutonomousAnswers("session", opened.runId)).rejects.toThrow("ANSWER_SCHEMA")
    expect(f.runtime.status("session").autonomous!.intent).toEqual(opened.autonomous.intent)
    expect(f.runtime.status("session").autonomous!.lifecycle).toBe("waiting_input")
  } finally { await f.cleanup() }
})

test("cancel aborts a pending question and a late user reply cannot enter a replacement Run", async () => {
  let reply!: (value: string[][]) => void
  let seenSignal: AbortSignal | undefined
  let started!: () => void
  const ready = new Promise<void>((resolve) => { started = resolve })
  const f = await fixture(undefined, { ask: ({ signal }) => { seenSignal = signal; started(); return new Promise((resolve) => { reply = resolve }) } })
  try {
    const opened = await f.open()
    await f.host.submitAutonomousDecision("session", opened.runId, "ask", { kind: "ask", reason: "information", questions: ["Which file?"] })
    const pending = f.host.requestAutonomousAnswers("session", opened.runId).then(() => undefined, (error: Error) => error.message)
    await ready
    await f.runtime.cancel("session")
    expect(await pending).toContain("QUESTION_CANCELLED")
    expect(seenSignal?.aborted).toBe(true)
    const replacement = await f.open()
    reply([["old answer"]])
    await Promise.resolve()
    expect(replacement.runId).not.toBe(opened.runId)
    expect(f.runtime.status("session").autonomous!.intent.requirements).toHaveLength(1)
  } finally { await f.cleanup() }
})
