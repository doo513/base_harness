import { expect, test } from "bun:test"
import type { DecisionAction, DecisionProposal, ObservationReport, SubjectRef } from "@base-harness/domain-contracts"
import { AutonomousRun, type AutonomousRunPorts, type AutonomousRunSetup } from "../src/autonomous-run"

const ref = (id: string, revision = 1) => ({ id, revision, sha256: "a".repeat(64) })
const report: SubjectRef & { kind: "report" } = { ...ref("report"), kind: "report" }
const source: SubjectRef = { ...ref("source"), kind: "source" }
const candidate: SubjectRef & { kind: "candidate" } = { ...ref("candidate"), kind: "candidate" }
const zero = { modelTokens: 0, costMinorUnits: 0 }

function fixture(options: { ports?: Partial<AutonomousRunPorts>; setup?: Partial<AutonomousRunSetup>; clock?: () => number; preparing?: boolean } = {}) {
  const now = options.clock ?? Date.now
  const setup: AutonomousRunSetup = {
    binding: { schemaVersion: "autonomous-run-binding-v1", runId: "run", semantics: "autonomous-v1", domainModule: ref("general"), executor: ref("executor"), authorityRef: ref("grant"), budgetId: "budget" },
    taskId: "root",
    intent: { schemaVersion: "intent-v1", ref: ref("intent"), originalRequest: source, requirements: [], constraints: [] },
    interpretation: { schemaVersion: "interpretation-v1", ref: ref("interpretation"), intentRef: ref("intent"), goalSummary: "Investigate", assumptions: [], openQuestions: [], proposedCheckIds: [] },
    authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId: "run", expiresAt: new Date(now() + 120_000).toISOString(),
      provenanceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }], capabilities: [{ operation: "read", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] }] },
    limits: { deadlineAt: new Date(now() + 60_000).toISOString(), maxActions: 10, maxParallelTasks: 1, maxTaskDepth: 0, maxTotalTasks: 1 },
    cleanupTimeoutMs: 200, metering: { tokens: false, cost: false }, subjects: [source, report], gates: [], gateEvidence: {},
    checks: [{ schemaVersion: "check-spec-v1", ref: ref("check"), author: "model", executorId: "python-measurement", parameters: {}, supportedSubjects: ["source"], requiredCapabilities: ["read"], timeoutMs: 1000 }],
    ...options.setup,
  }
  const owned = new WeakSet<object>()
  const ports: AutonomousRunPorts = {
    resolveEffects: async () => [{ operation: "read", targets: [{ kind: "workspace_path", selector: "/work/file" }] }],
    invoke: async () => ({ text: "actual read result" }),
    measure: async (proposal) => {
      const observation: ObservationReport = {
        schemaVersion: "observation-v1", observationId: `obs:${proposal.decisionId}`, requestId: proposal.decisionId, runId: "run", taskId: "root", subject: source,
        checkRef: ref("check"), environmentHash: "b".repeat(64), startedAt: new Date(now()).toISOString(), finishedAt: new Date(now()).toISOString(),
        producer: { kind: "verifier", id: "python-measurement", revision: "5" }, artifacts: [], limitations: [],
        result: { execution: "completed", findings: [{ kind: "comparison", name: "test", operator: "equals", expected: 0, observed: 1, result: "fail" }] },
      }
      owned.add(observation)
      return observation
    },
    authenticates: (value) => owned.has(value),
    revise: ({ basedOnRef, ...proposal }) => ({ ...proposal, ref: ref(basedOnRef.id, basedOnRef.revision + 1) }),
    cleanup: async () => [],
    ...options.ports,
  }
  const run = new AutonomousRun(setup, ports, now)
  if (!options.preparing) run.prepare({ status: "proceed", context: {} })
  const decision = (id: string, action: DecisionAction, observationIds: string[] = []): DecisionProposal => ({
    schemaVersion: "decision-v1", decisionId: id, basis: run.basis(), observationIds, action,
  })
  const finish = (status: "partial" | "satisfied" | "not_assessed" = "partial", openWork: "drain" | "cancel" = "drain"): DecisionAction => ({
    kind: "finish", report, openWork, assessment: { status, summary: "Findings", citedObservationIds: [], uncertainties: ["Unresolved cause"] },
  })
  return { run, decision, finish, setup }
}
const read: DecisionAction = { kind: "invoke", toolId: "read", arguments: { path: "/work/file" } }
const measure: DecisionAction = { kind: "measure", checkRef: ref("check"), subject: source }

test("failed observation leaves the Run active for model-selected investigation or partial finish", async () => {
  const { run, decision, finish } = fixture()
  const measured = await run.submit(decision("measure", measure))
  expect(measured.accepted).toBe(true)
  expect(run.snapshot().lifecycle).toBe("active")
  expect((await run.submit(decision("investigate", read, ["obs:measure"]))).accepted).toBe(true)
  expect((await run.submit(decision("finish", finish(), ["obs:measure"]))).accepted).toBe(true)
  const final = run.snapshot().completion!
  expect(final.reason).toBe("requested")
  expect(final.assessment?.status).toBe("partial")
  expect(final.observationIds).toEqual(["obs:measure"])
  expect(final).not.toHaveProperty("readyEligible")
})

test("Prepare and questions suspend action dispatch without consuming tool budget", async () => {
  const { run, decision } = fixture({ preparing: true })
  expect((await run.submit(decision("early", read))).accepted).toBe(false)
  run.prepare({ status: "needs_input", reason: "information", questions: ["Which file?"] })
  expect((await run.submit(decision("waiting", read))).accepted).toBe(false)
  expect(run.snapshot().budget.actions).toBe(0)
  expect(() => run.resume(undefined as never)).toThrow()
  const before = run.snapshot()
  const intent = { ...before.intent, ref: ref(before.intent.ref.id, 2), requirements: [{ id: "answer", text: "file",
    sourceRefs: [{ sourceId: "answer", sha256: "a".repeat(64) }] }] }
  const interpretation = { ...before.interpretation, ref: ref(before.interpretation.ref.id, 2), intentRef: intent.ref }
  run.resume({ basedOn: run.basis(), questionRevision: before.questionRevision, intent, interpretation })
  run.prepare({ status: "proceed", context: {} })
  expect((await run.submit(decision("after-answer", read))).accepted).toBe(true)
  await run.terminate("cancelled")
})

test("no gate means unmeasured satisfied is a model assessment, not verifier success", async () => {
  const { run, decision, finish } = fixture()
  await run.submit(decision("finish", finish("satisfied")))
  expect(run.snapshot().completion).toMatchObject({ reason: "requested", assessment: { status: "satisfied" }, observationIds: [] })
})

test("explicit missing gate refuses satisfied but permits partial termination", async () => {
  const { run, decision, finish } = fixture({ setup: {
    gates: [{ id: "required", source: "explicit_user", sourceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }], action: "finish_satisfied", checkRef: ref("check"), requiredComparisons: ["test"] }],
    gateEvidence: { required: { subject: source, environmentHash: "b".repeat(64) } },
  } })
  expect(await run.submit(decision("satisfied", finish("satisfied")))).toEqual({ accepted: false, code: "AUTONOMOUS_GATE_UNSATISFIED" })
  expect(run.snapshot().lifecycle).toBe("active")
  expect((await run.submit(decision("partial", finish()))).accepted).toBe(true)
  expect(run.snapshot().completion?.gates[0]?.state).toBe("unknown")
})

const candidateSeal = () => ({
  candidate,
  taskId: "root",
  receipt: {
    receiptId: "receipt",
    runId: "run",
    authorityRef: ref("grant"),
    candidate,
    baselineHash: "c".repeat(64),
    patchHash: "d".repeat(64),
  },
  files: [{ path: "/work/file", beforeHash: "e".repeat(64), afterHash: "f".repeat(64) }],
})

test("a failed observation does not become an implicit apply gate", async () => {
  const now = Date.now()
  const { run, decision } = fixture({
    setup: {
      subjects: [source, report, candidate],
      authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId: "run",
        expiresAt: new Date(now + 120_000).toISOString(),
        provenanceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }],
        capabilities: [
          { operation: "read", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
          { operation: "mutate", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
          { operation: "publish", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
        ] },
      checks: [{ schemaVersion: "check-spec-v1", ref: ref("candidate-check"), author: "model",
        executorId: "python-measurement", parameters: {}, supportedSubjects: ["candidate"],
        requiredCapabilities: ["read"], timeoutMs: 1000 }],
    },
    ports: {
      resolveEffects: async (action) => action.kind === "invoke"
        ? [{ operation: "mutate", targets: [{ kind: "workspace_path", selector: "/work/file" }] }]
        : action.kind === "apply_candidate"
          ? [{ operation: "publish", targets: [{ kind: "workspace_path", selector: "/work/file" }] }]
          : [{ operation: "read", targets: [{ kind: "workspace_path", selector: "/work/file" }] }],
      beginMutation: async () => {},
      sealCandidate: async () => candidateSeal(),
      measure: async (proposal) => ({
        schemaVersion: "observation-v1", observationId: "candidate-failed", requestId: proposal.decisionId,
        runId: "run", taskId: "root", subject: candidate, checkRef: ref("candidate-check"),
        environmentHash: "b".repeat(64), startedAt: new Date(now).toISOString(), finishedAt: new Date(now).toISOString(),
        producer: { kind: "verifier", id: "python-measurement", revision: "5" }, artifacts: [], limitations: [],
        result: { execution: "completed", findings: [{ kind: "comparison", name: "test", operator: "equals",
          expected: 0, observed: 1, result: "fail" }] },
      }),
      authenticates: () => true,
      applyCandidate: async () => ({ candidate, state: "applied", unresolvedEffects: [] }),
    },
  })
  expect((await run.submit(decision("mutate", { kind: "invoke", toolId: "write", arguments: {} }))).accepted).toBe(true)
  expect((await run.submit(decision("measure-candidate", { kind: "measure", subject: candidate,
    checkRef: ref("candidate-check") }))).accepted).toBe(true)
  expect((await run.submit(decision("apply-failed-observation", { kind: "apply_candidate", candidate }))).accepted).toBe(true)
  expect(run.snapshot().candidates[0]?.state).toBe("applied")
  await run.terminate("cancelled")
})

test("an explicit failed apply gate retains the Candidate and permits a partial finish", async () => {
  const { run, decision, finish } = fixture({
    setup: {
      subjects: [source, report, candidate],
      authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId: "run",
        expiresAt: new Date(Date.now() + 120_000).toISOString(),
        provenanceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }],
        capabilities: [
          { operation: "mutate", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
          { operation: "publish", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
        ] },
      gates: [{ id: "apply-required", source: "explicit_user",
        sourceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }], action: "apply_candidate",
        checkRef: ref("candidate-check"), requiredComparisons: ["test"] }],
      gateEvidence: { "apply-required": { subject: candidate, environmentHash: "b".repeat(64) } },
    },
    ports: {
      resolveEffects: async (action) => [{
        operation: action.kind === "apply_candidate" ? "publish" : "mutate",
        targets: [{ kind: "workspace_path", selector: "/work/file" }],
      }],
      beginMutation: async () => {},
      sealCandidate: async () => candidateSeal(),
      applyCandidate: async () => ({ candidate, state: "applied", unresolvedEffects: [] }),
    },
  })
  await run.submit(decision("mutate", { kind: "invoke", toolId: "write", arguments: {} }))
  expect(await run.submit(decision("blocked-apply", { kind: "apply_candidate", candidate })))
    .toEqual({ accepted: false, code: "AUTONOMOUS_GATE_UNSATISFIED" })
  expect(run.snapshot().candidates[0]?.state).toBe("sealed")
  expect((await run.submit(decision("partial-with-retained", finish()))).accepted).toBe(true)
  expect(run.snapshot().completion?.candidateDispositions[0]?.state).toBe("retained")
})

test("publication recovery_required closes as runtime_fault and preserves unresolved effects", async () => {
  const { run, decision } = fixture({
    setup: {
      subjects: [source, report, candidate],
      authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId: "run",
        expiresAt: new Date(Date.now() + 120_000).toISOString(),
        provenanceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }],
        capabilities: [
          { operation: "mutate", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
          { operation: "publish", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
        ] },
    },
    ports: {
      resolveEffects: async (action) => [{
        operation: action.kind === "apply_candidate" ? "publish" : "mutate",
        targets: [{ kind: "workspace_path", selector: "/work/file" }],
      }],
      beginMutation: async () => {},
      sealCandidate: async () => candidateSeal(),
      applyCandidate: async () => ({ candidate, state: "recovery_required", journalPath: "/state/journal.json",
        unresolvedEffects: ["rollback incomplete for /work/file"] }),
    },
  })
  await run.submit(decision("mutate", { kind: "invoke", toolId: "write", arguments: {} }))
  expect(await run.submit(decision("apply-recovery", { kind: "apply_candidate", candidate })))
    .toEqual({ accepted: false, code: "AUTONOMOUS_CANDIDATE_RECOVERY_REQUIRED" })
  expect(run.snapshot()).toMatchObject({
    lifecycle: "closed",
    candidates: [{ state: "recovery_required", journalPath: "/state/journal.json" }],
    completion: { reason: "runtime_fault", candidateDispositions: [{ state: "recovery_required" }],
      unresolvedEffects: ["rollback incomplete for /work/file"] },
  })
})

test("finish drain rejects its old basis when an admitted apply changes Candidate state", async () => {
  let started!: () => void
  let release!: () => void
  const applying = new Promise<void>((resolve) => { started = resolve })
  const { run, decision, finish } = fixture({
    setup: {
      subjects: [source, report, candidate],
      authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId: "run",
        expiresAt: new Date(Date.now() + 120_000).toISOString(),
        provenanceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }],
        capabilities: [
          { operation: "mutate", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
          { operation: "publish", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
        ] },
    },
    ports: {
      resolveEffects: async (action) => [{
        operation: action.kind === "apply_candidate" ? "publish" : "mutate",
        targets: [{ kind: "workspace_path", selector: "/work/file" }],
      }],
      beginMutation: async () => {},
      sealCandidate: async () => candidateSeal(),
      applyCandidate: async () => {
        started()
        await new Promise<void>((resolve) => { release = resolve })
        return { candidate, state: "applied", unresolvedEffects: [] }
      },
    },
  })
  await run.submit(decision("mutate", { kind: "invoke", toolId: "write", arguments: {} }))
  const apply = run.submit(decision("apply-running", { kind: "apply_candidate", candidate }))
  await applying
  const close = run.submit(decision("finish-during-apply", finish()))
  await Promise.resolve()
  expect(run.snapshot().candidates[0]?.state).toBe("applying")
  release()
  expect((await apply).accepted).toBe(true)
  expect(await close).toEqual({ accepted: false, code: "FINISH_BASIS_CHANGED" })
  expect(run.snapshot()).toMatchObject({ lifecycle: "active", candidates: [{ state: "applied" }] })
  expect(run.snapshot().completion).toBeUndefined()
  await run.terminate("cancelled")
})

test("cleanup timeout never records an applying Candidate as normally settled", async () => {
  let started!: () => void
  let release!: () => void
  const applying = new Promise<void>((resolve) => { started = resolve })
  const { run, decision } = fixture({
    setup: {
      cleanupTimeoutMs: 10,
      subjects: [source, report, candidate],
      authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId: "run",
        expiresAt: new Date(Date.now() + 120_000).toISOString(),
        provenanceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }],
        capabilities: [
          { operation: "mutate", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
          { operation: "publish", targets: [{ kind: "workspace_path", selector: "/work" }], exclusions: [] },
        ] },
    },
    ports: {
      resolveEffects: async (action) => [{
        operation: action.kind === "apply_candidate" ? "publish" : "mutate",
        targets: [{ kind: "workspace_path", selector: "/work/file" }],
      }],
      beginMutation: async () => {},
      sealCandidate: async () => candidateSeal(),
      applyCandidate: async () => {
        started()
        await new Promise<void>((resolve) => { release = resolve })
        return { candidate, state: "applied", unresolvedEffects: [] }
      },
    },
  })
  await run.submit(decision("mutate", { kind: "invoke", toolId: "write", arguments: {} }))
  const apply = run.submit(decision("apply-ignores-cancel", { kind: "apply_candidate", candidate }))
  await applying
  const completion = await run.terminate("cancelled")
  expect(completion).toMatchObject({
    reason: "runtime_fault",
    candidateDispositions: [{ state: "recovery_required" }],
  })
  expect(completion.unresolvedEffects).toContain("Cleanup not confirmed: decision:apply-ignores-cancel")
  release()
  expect(await apply).toEqual({ accepted: false, code: "AUTONOMOUS_STALE_RESULT" })
  expect(run.snapshot().candidates[0]?.state).toBe("recovery_required")
})

test("duplicate concurrent decisions dispatch once; changed payload is a conflict", async () => {
  let invoked = 0
  const { run, decision } = fixture({ ports: { invoke: async () => { invoked++; return "read" } } })
  const proposal = decision("same", read)
  const outcomes = await Promise.all([run.submit(proposal), run.submit(structuredClone(proposal))])
  expect(invoked).toBe(1)
  expect(outcomes[0]).toEqual(outcomes[1])
  expect(await run.submit({ ...proposal, action: { ...read, toolId: "different" } })).toEqual({ accepted: false, code: "AUTONOMOUS_REQUEST_CONFLICT" })
  await run.terminate("cancelled")
})

test("interpretation revision preserves original intent, observations and cumulative budget", async () => {
  const { run, decision } = fixture()
  await run.submit(decision("measurement", measure))
  const stale = decision("stale", read)
  const basis = run.basis()
  const revised = decision("revise", { kind: "revise_interpretation", proposal: {
    schemaVersion: "interpretation-v1", basedOnRef: basis.interpretationRef, intentRef: basis.intentRef,
    goalSummary: "A different hypothesis", assumptions: [], openQuestions: [], proposedCheckIds: [],
  } })
  expect((await run.submit(revised)).accepted).toBe(true)
  expect(run.basis().interpretationRef.revision).toBe(2)
  expect(run.snapshot().observations).toHaveLength(1)
  expect(run.snapshot().budget.actions).toBe(1)
  expect(await run.submit(stale)).toEqual({ accepted: false, code: "AUTONOMOUS_STALE_BASIS" })
  await run.terminate("cancelled")
})

test("cancelled late tool output cannot update completion or another Run", async () => {
  let release!: () => void
  let started!: () => void
  const running = new Promise<void>((resolve) => { started = resolve })
  const { run, decision } = fixture({ ports: { invoke: async () => {
    started(); await new Promise<void>((resolve) => { release = resolve }); return "late"
  } } })
  const pending = run.submit(decision("read", read))
  await running
  const termination = run.terminate("cancelled")
  release()
  expect((await pending).accepted).toBe(false)
  expect((await termination).reason).toBe("cancelled")
  expect(run.snapshot().completion?.assessment).toBeNull()
  expect(run.snapshot().lateResultIds).toEqual(["read"])
  const replacement = fixture()
  const old = decision("old-run", read); old.basis.runId = "prior-run"
  expect((await replacement.run.submit(old)).accepted).toBe(false)
  await replacement.run.terminate("cancelled")
})

test("finish drain admits no new work and waits for already dispatched actions", async () => {
  let release!: () => void
  let started!: () => void
  const running = new Promise<void>((resolve) => { started = resolve })
  const { run, decision, finish } = fixture({ ports: { invoke: async () => {
    started(); await new Promise<void>((resolve) => { release = resolve }); return "read"
  } } })
  const pending = run.submit(decision("read", read))
  await running
  const ending = run.submit(decision("finish", finish()))
  await Promise.resolve(); await Promise.resolve()
  expect(run.snapshot().lifecycle).toBe("closing")
  expect((await run.submit(decision("new", read))).accepted).toBe(false)
  release(); await pending
  expect((await ending).accepted).toBe(true)
  expect(run.snapshot().lifecycle).toBe("closed")
})

test("cancel overrides an in-flight requested drain", async () => {
  let release!: () => void
  let started!: () => void
  const running = new Promise<void>((resolve) => { started = resolve })
  const { run, decision, finish } = fixture({ ports: { invoke: async () => {
    started(); await new Promise<void>((resolve) => { release = resolve }); return "read"
  } } })
  const pending = run.submit(decision("read", read)); await running
  const ending = run.submit(decision("finish", finish()))
  await Promise.resolve(); await Promise.resolve()
  const cancelled = run.terminate("cancelled"); release()
  await pending; await ending
  expect((await cancelled).reason).toBe("cancelled")
})

test("report revision change while draining rejects the old finish basis", async () => {
  let release!: () => void
  let started!: () => void
  const running = new Promise<void>((resolve) => { started = resolve })
  const { run, decision, finish } = fixture({ ports: { invoke: async () => {
    started(); await new Promise<void>((resolve) => { release = resolve }); return "read"
  } } })
  const pending = run.submit(decision("read", read)); await running
  const ending = run.submit(decision("finish", finish()))
  await Promise.resolve(); await Promise.resolve()
  run.registerSubject({ ...report, revision: 2 })
  release(); await pending
  expect(await ending).toEqual({ accepted: false, code: "FINISH_BASIS_CHANGED" })
  expect(run.snapshot().completion).toBeUndefined()
  expect(run.snapshot().lifecycle).toBe("active")
  await run.terminate("cancelled")
})

test("model and tool calls share one limit; exhaustion closes without a paid final call", async () => {
  const base = fixture()
  await base.run.terminate("cancelled")
  const { run, decision } = fixture({ setup: { limits: { ...base.setup.limits, maxActions: 1 } } })
  await run.reserveModel("prepare", {}, zero)
  await run.settleModel("prepare", zero)
  expect((await run.submit(decision("read", read))).accepted).toBe(false)
  expect(run.snapshot().completion).toMatchObject({ reason: "budget_exhausted", assessment: null })
})

test("deadline during input wait closes with no fabricated assessment", async () => {
  let now = Date.now()
  const { run, decision } = fixture({ clock: () => now })
  await run.submit(decision("ask", { kind: "ask", reason: "information", questions: ["Which repository?"] }))
  now += 60_001
  await run.terminate("deadline_exceeded")
  expect(run.snapshot().completion).toMatchObject({ reason: "deadline_exceeded", assessment: null })
})

test("unconfirmed cleanup yields runtime_fault with unresolved effects, never normal completion", async () => {
  const { run, decision, finish } = fixture({ setup: { cleanupTimeoutMs: 10 }, ports: { cleanup: () => new Promise(() => {}) } })
  await run.submit(decision("finish", finish()))
  expect(run.snapshot().completion).toMatchObject({ reason: "runtime_fault", assessment: null })
  expect(run.snapshot().completion!.unresolvedEffects.length).toBeGreaterThan(0)
})

test("drain timeout invokes executor cleanup even when an action ignores cancellation", async () => {
  let cleanups = 0
  let release!: () => void
  let started!: () => void
  const ready = new Promise<void>((resolve) => { started = resolve })
  const { run, decision, finish } = fixture({ setup: { cleanupTimeoutMs: 10 }, ports: {
    invoke: () => { started(); return new Promise((resolve) => { release = () => resolve("late output") }) },
    cleanup: async () => { cleanups++; return [] },
  } })
  const pending = run.submit(decision("read", read))
  await ready
  await run.submit(decision("finish", finish()))
  expect(cleanups).toBe(1)
  expect(run.snapshot().completion).toMatchObject({ reason: "runtime_fault", assessment: null })
  expect(run.snapshot().completion!.unresolvedEffects).toContain("Cleanup not confirmed: decision:read")
  release()
  expect(await pending).toEqual({ accepted: false, code: "AUTONOMOUS_STALE_RESULT" })
  expect(cleanups).toBe(1)
})

test("untrusted observation cannot become a trusted fact or trigger automatic repair", async () => {
  const { run, decision } = fixture({ ports: { authenticates: () => false } })
  expect(await run.submit(decision("measure", measure))).toEqual({ accepted: false, code: "AUTONOMOUS_OBSERVATION_INTEGRITY" })
  expect(run.snapshot().observations).toHaveLength(0)
  expect(run.snapshot().completion?.reason).toBe("runtime_fault")
})

test("measurement service error is feedback; a partial finish remains available", async () => {
  const { run, decision, finish } = fixture({ ports: { measure: async () => { throw new Error("MEASUREMENT_PROCESS_EXITED") } } })
  expect((await run.submit(decision("measure", measure))).accepted).toBe(false)
  expect(run.snapshot().lifecycle).toBe("active")
  expect((await run.submit(decision("partial", finish()))).accepted).toBe(true)
})

test("measurement response corruption closes the Run as a runtime fault", async () => {
  const { run, decision } = fixture({ ports: { measure: async () => { throw new Error("MEASUREMENT_RESPONSE_PROTOCOL") } } })
  expect(await run.submit(decision("measure", measure))).toEqual({ accepted: false, code: "MEASUREMENT_RESPONSE_PROTOCOL" })
  expect(run.snapshot()).toMatchObject({ lifecycle: "closed", completion: { reason: "runtime_fault", assessment: null } })
})
