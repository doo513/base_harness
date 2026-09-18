import type {
  AutonomousPreparationResult, CompletionRecord, DecisionBasis, DecisionProposal, GateResult, Json, ObservationReport,
  RunLifecycle, SubjectRef, CheckSpec, TerminationReason, AutonomousRunSetup, AutonomousRunPorts, AutonomousDecisionResult, AutonomousRunSnapshot, AutonomousClarification, AutonomousIntentRevision,
} from "@base-harness/domain-contracts"
import {
  admitDecision, assertAutonomousSchema, canonicalJson, evaluateActionGate, parseDecisionProposal, sameRef,
  validateAuthority, type ActionEffect, type DecisionAdmissionContext,
} from "@base-harness/kernel"
import { AutonomousBudget, type ResourceUsage } from "./autonomous-budget"

export type { AutonomousRunSetup, AutonomousRunPorts, AutonomousDecisionResult } from "@base-harness/domain-contracts"

interface PendingAction {
  controller: AbortController
  settled: Promise<void>
  settle(): void
}

/** One controller owned by the existing Coordinator RunRecord. Not an agent loop,
 * repository, global authority service, or source of semantic repair decisions.
 */
export class AutonomousRun {
  private readonly setup: AutonomousRunSetup
  readonly budget: AutonomousBudget
  private lifecycle: RunLifecycle = "preparing"
  private readonly decisions = new Map<string, { fingerprint: string; result: Promise<AutonomousDecisionResult> }>()
  private readonly pending = new Map<string, PendingAction>()
  private readonly observations: ObservationReport[] = []
  private readonly lateResults: string[] = []
  private questions: string[] = []
  private questionRevision = 0
  private preparation?: { basis: DecisionBasis; context: Json }
  private completion?: CompletionRecord
  private closing?: Promise<CompletionRecord | undefined>
  private deadline: ReturnType<typeof setTimeout>
  private terminationRequested?: Exclude<TerminationReason, "requested">

  constructor(setup: AutonomousRunSetup, private readonly ports: AutonomousRunPorts, private readonly clock: () => number = Date.now,
    private readonly onClosed?: () => void) {
    assertAutonomousSchema("intent", setup.intent)
    assertAutonomousSchema("interpretation", setup.interpretation)
    validateAuthority(setup.authority, setup.binding.runId, clock())
    if (setup.binding.semantics !== "autonomous-v1" || setup.binding.schemaVersion !== "autonomous-run-binding-v1" ||
        !sameRef(setup.binding.authorityRef, setup.authority.ref) || !sameRef(setup.interpretation.intentRef, setup.intent.ref) ||
        !setup.taskId.trim() || !Number.isSafeInteger(setup.cleanupTimeoutMs) || setup.cleanupTimeoutMs <= 0) {
      throw new Error("AUTONOMOUS_RUN_BINDING")
    }
    for (const ref of [setup.binding.domainModule, setup.binding.executor]) assertAutonomousSchema("ref", ref)
    for (const check of setup.checks) assertAutonomousSchema("check", check)
    for (const gate of setup.gates) assertAutonomousSchema("gate", gate)
    for (const subject of setup.subjects) assertAutonomousSchema("subject", subject)
    this.setup = structuredClone(setup)
    this.budget = new AutonomousBudget(setup.binding.budgetId, setup.limits, setup.metering, clock)
    // Clamp JS timers but keep the true deadline in the ledger; rescheduling is
    // a clock mechanism, not a reset of the user's elapsed-time budget.
    const tick = () => {
      if (this.lifecycle === "closed") return
      const remaining = Date.parse(this.setup.limits.deadlineAt) - this.clock()
      if (remaining <= 0) void this.terminate("deadline_exceeded")
      else {
        this.deadline = setTimeout(tick, Math.min(remaining, 2_147_483_647))
        this.deadline.unref?.()
      }
    }
    this.deadline = setTimeout(tick, Math.min(Date.parse(setup.limits.deadlineAt) - clock(), 2_147_483_647))
    this.deadline.unref?.()
  }

  basis(): DecisionBasis {
    return { runId: this.setup.binding.runId, taskId: this.setup.taskId, taskRevision: 1,
      intentRef: structuredClone(this.setup.intent.ref), interpretationRef: structuredClone(this.setup.interpretation.ref),
      authorityRef: structuredClone(this.setup.authority.ref) }
  }

  snapshot(): AutonomousRunSnapshot {
    return structuredClone({ semantics: "autonomous-v1" as const, lifecycle: this.lifecycle, binding: this.setup.binding,
      intent: this.setup.intent, interpretation: this.setup.interpretation, authority: this.setup.authority,
      ...(this.preparation ? { preparation: this.preparation } : {}),
      observations: this.observations, questions: this.questions, questionRevision: this.questionRevision, completion: this.completion,
      pendingDecisionIds: [...this.pending.keys()], lateResultIds: this.lateResults, budget: this.budget.snapshot() })
  }

  prepare(result: AutonomousPreparationResult): void {
    if (this.lifecycle !== "preparing") throw new Error("AUTONOMOUS_PREPARE_STATE")
    assertAutonomousSchema("preparation", result)
    if (result.status === "invalid") throw new Error(result.code)
    this.preparation = result.status === "proceed"
      ? { basis: this.basis(), context: structuredClone(result.context) }
      : undefined
    this.questions = result.status === "needs_input" ? [...result.questions] : []
    if (this.questions.length) this.questionRevision++
    this.lifecycle = result.status === "needs_input" ? "waiting_input" : "active"
  }

  /** Only Host's authenticated question-answer path calls this, not a model tool. */
  resume(clarification: AutonomousClarification): void {
    if (this.lifecycle !== "waiting_input") throw new Error("AUTONOMOUS_RESUME_STATE")
    if (!clarification) throw new Error("AUTONOMOUS_CLARIFICATION_REQUIRED")
    this.budget.assertAvailable()
    const { intent, interpretation } = clarification
    assertAutonomousSchema("intent", intent)
    assertAutonomousSchema("interpretation", interpretation)
    if (canonicalJson(clarification.basedOn) !== canonicalJson(this.basis()) || clarification.questionRevision !== this.questionRevision ||
        intent.ref.id !== this.setup.intent.ref.id || intent.ref.revision !== this.setup.intent.ref.revision + 1 ||
        canonicalJson(intent.originalRequest) !== canonicalJson(this.setup.intent.originalRequest) ||
        canonicalJson(intent.constraints) !== canonicalJson(this.setup.intent.constraints) ||
        intent.requirements.length <= this.setup.intent.requirements.length ||
        canonicalJson(intent.requirements.slice(0, this.setup.intent.requirements.length)) !== canonicalJson(this.setup.intent.requirements) ||
        interpretation.ref.id !== this.setup.interpretation.ref.id || interpretation.ref.revision !== this.setup.interpretation.ref.revision + 1 ||
        !sameRef(interpretation.intentRef, intent.ref)) throw new Error("AUTONOMOUS_CLARIFICATION_BINDING")
    this.setup.intent = structuredClone(intent)
    this.setup.interpretation = structuredClone(interpretation)
    this.preparation = undefined
    this.questions = []
    this.lifecycle = "preparing"
  }

  /** A new authenticated user message revises intent, never authority or budget. */
  reviseIntent(revision: AutonomousIntentRevision): void {
    if (this.lifecycle !== "active") throw new Error("AUTONOMOUS_INTENT_REVISION_STATE")
    this.budget.assertAvailable()
    const { intent, interpretation } = revision
    assertAutonomousSchema("intent", intent)
    assertAutonomousSchema("interpretation", interpretation)
    const { ref: oldInterpretationRef, intentRef: oldIntentRef, ...oldInterpretation } = this.setup.interpretation
    const { ref: newInterpretationRef, intentRef: newIntentRef, ...newInterpretation } = interpretation
    if (canonicalJson(revision.basedOn) !== canonicalJson(this.basis()) ||
        intent.ref.id !== this.setup.intent.ref.id || intent.ref.revision !== this.setup.intent.ref.revision + 1 ||
        canonicalJson(intent.originalRequest) !== canonicalJson(this.setup.intent.originalRequest) ||
        canonicalJson(intent.constraints) !== canonicalJson(this.setup.intent.constraints) ||
        intent.requirements.length <= this.setup.intent.requirements.length ||
        canonicalJson(intent.requirements.slice(0, this.setup.intent.requirements.length)) !== canonicalJson(this.setup.intent.requirements) ||
        newInterpretationRef.id !== oldInterpretationRef.id || newInterpretationRef.revision !== oldInterpretationRef.revision + 1 ||
        !sameRef(newIntentRef, intent.ref) || canonicalJson(newInterpretation) !== canonicalJson(oldInterpretation) ||
        !sameRef(oldIntentRef, this.setup.intent.ref)) throw new Error("AUTONOMOUS_INTENT_REVISION_BINDING")
    this.setup.intent = structuredClone(intent)
    this.setup.interpretation = structuredClone(interpretation)
    this.preparation = undefined
    this.lifecycle = "preparing"
  }

  registerSubject(subject: SubjectRef): void {
    if (this.lifecycle === "closed") throw new Error("AUTONOMOUS_RUN_CLOSED")
    assertAutonomousSchema("subject", subject)
    const index = this.setup.subjects.findIndex((item) => item.id === subject.id)
    if (index >= 0) {
      const current = this.setup.subjects[index]!
      if (sameRef(current, subject) && current.kind === subject.kind) return
      if (subject.kind !== current.kind || subject.revision <= current.revision) throw new Error("AUTONOMOUS_SUBJECT_REVISION")
      this.setup.subjects[index] = structuredClone(subject)
      for (const evidence of Object.values(this.setup.gateEvidence)) {
        if (evidence.subject.id === subject.id) evidence.subject = structuredClone(subject)
      }
    } else this.setup.subjects.push(structuredClone(subject))
  }

  registerCheck(check: CheckSpec): void {
    if (this.lifecycle === "closed" || this.lifecycle === "closing") throw new Error("AUTONOMOUS_RUN_CLOSED")
    assertAutonomousSchema("check", check)
    if (this.setup.checks.some((item) => item.ref.id === check.ref.id)) throw new Error("AUTONOMOUS_CHECK_DUPLICATE")
    this.setup.checks.push(structuredClone(check))
  }

  /** Called before every actual model/Prepare invocation in the existing loop. */
  async reserveModel(requestId: string, payload: Json, upperBound: ResourceUsage): Promise<"reserved" | "replay"> {
    if (!["active", "preparing"].includes(this.lifecycle)) throw new Error("AUTONOMOUS_MODEL_STATE")
    try {
      const state = this.budget.reserve(`model:${requestId}`, payload, upperBound)
      if (state === "reserved") this.pending.set(`model:${requestId}`, this.newPending())
      return state
    }
    catch (error) { await this.resourceFailure(error); throw error }
  }

  modelSignal(requestId: string): AbortSignal {
    const pending = this.pending.get(`model:${requestId}`)
    if (!pending) throw new Error("AUTONOMOUS_MODEL_NOT_RESERVED")
    return pending.controller.signal
  }

  async settleModel(requestId: string, usage: ResourceUsage): Promise<void> {
    const key = `model:${requestId}`
    const pending = this.pending.get(key)
    this.pending.delete(key)
    pending?.settle()
    try { this.budget.settle(key, usage) }
    catch (error) { await this.terminate("runtime_fault"); throw error }
  }

  private newPending(): PendingAction {
    let settle!: () => void
    return { controller: new AbortController(), settled: new Promise<void>((resolve) => { settle = resolve }), settle: () => settle() }
  }

  submit(value: unknown): Promise<AutonomousDecisionResult> {
    let proposal: DecisionProposal
    try { proposal = parseDecisionProposal(value) } catch { return Promise.resolve({ accepted: false, code: "AUTONOMOUS_DECISION_SCHEMA" }) }
    const fingerprint = canonicalJson(proposal)
    const previous = this.decisions.get(proposal.decisionId)
    if (previous) return previous.fingerprint === fingerprint ? previous.result : Promise.resolve({ accepted: false, code: "AUTONOMOUS_REQUEST_CONFLICT" })
    const result = Promise.resolve().then(() => this.execute(proposal))
    this.decisions.set(proposal.decisionId, { fingerprint, result })
    return result
  }

  private context(proposal: DecisionProposal, effects: ActionEffect[]): DecisionAdmissionContext {
    return { basis: this.basis(), lifecycle: this.lifecycle, now: this.clock(), authority: this.setup.authority,
      observations: this.observations, subjects: this.setup.subjects, checks: this.setup.checks, gates: this.setup.gates,
      gateEvidence: this.setup.gateEvidence, supportedActions: ["invoke", "measure", "ask", "revise_interpretation", "finish"],
      resolvedAction: { canonicalAction: canonicalJson(proposal.action), effects } }
  }

  private async execute(proposal: DecisionProposal): Promise<AutonomousDecisionResult> {
    const { action, decisionId } = proposal
    // Reject stale state before effect resolution (which may consult adapter metadata).
    const initial = admitDecision(proposal, this.context(proposal, []))
    if (!initial.accepted && initial.code !== "AUTONOMOUS_EFFECT_INCOMPLETE") return initial
    let effects: ActionEffect[]
    try { effects = action.kind === "invoke" || action.kind === "measure" ? await this.ports.resolveEffects(structuredClone(action)) : [] }
    catch { return { accepted: false, code: "AUTONOMOUS_CAPABILITY_UNSUPPORTED" } }
    const admitted = admitDecision(proposal, this.context(proposal, effects))
    if (!admitted.accepted) return admitted
    // M4 connects mutations/publication to Candidate admission. Until then they
    // cannot accidentally fall through a read/measurement-only new path.
    if (effects.some((effect) => effect.operation === "mutate" || effect.operation === "publish" || effect.operation === "delegate")) {
      return { accepted: false, code: "AUTONOMOUS_CAPABILITY_UNSUPPORTED" }
    }
    try { this.budget.assertAvailable() } catch (error) {
      await this.resourceFailure(error)
      return { accepted: false, code: error instanceof Error ? error.message : "AUTONOMOUS_RESOURCE_FAILURE" }
    }
    if (action.kind === "ask") {
      this.questions = [...action.questions]
      this.questionRevision++
      this.lifecycle = "waiting_input"
      return { accepted: true, decisionId }
    }
    if (action.kind === "revise_interpretation") {
      const updated = this.ports.revise(structuredClone(action.proposal))
      assertAutonomousSchema("interpretation", updated)
      if (updated.ref.id !== this.setup.interpretation.ref.id || updated.ref.revision !== this.setup.interpretation.ref.revision + 1 ||
          !sameRef(updated.intentRef, this.setup.intent.ref)) throw new Error("AUTONOMOUS_HOST_REVISION_INVALID")
      this.setup.interpretation = structuredClone(updated)
      this.preparation = undefined
      return { accepted: true, decisionId }
    }
    if (action.kind === "finish") {
      const completion = await this.close("requested", proposal)
      return completion ? { accepted: true, decisionId, completion: structuredClone(completion) } :
        { accepted: false, code: "FINISH_BASIS_CHANGED" }
    }
    if (action.kind !== "invoke" && action.kind !== "measure") return { accepted: false, code: "AUTONOMOUS_CAPABILITY_UNSUPPORTED" }
    try { this.budget.reserve(`decision:${decisionId}`, proposal, { modelTokens: 0, costMinorUnits: 0 }) }
    catch (error) {
      await this.resourceFailure(error)
      return { accepted: false, code: error instanceof Error ? error.message : "AUTONOMOUS_RESOURCE_FAILURE" }
    }
    const pending = this.newPending()
    const pendingId = `decision:${decisionId}`
    this.pending.set(pendingId, pending)
    try {
      // Admission and dispatch are synchronous up to the call. No actor-created
      // permit is accepted, and a concurrent cancel invalidates this owned signal.
      if (action.kind === "measure") {
        const observation = await this.ports.measure(structuredClone(proposal), pending.controller.signal)
        if (pending.controller.signal.aborted || this.lifecycle === "closed") {
          this.lateResults.push(decisionId)
          return { accepted: false, code: "AUTONOMOUS_STALE_RESULT" }
        }
        if (!this.ports.authenticates(observation) || observation.runId !== proposal.basis.runId ||
            observation.taskId !== proposal.basis.taskId || observation.requestId !== decisionId ||
            !sameRef(observation.subject, action.subject) || observation.subject.kind !== action.subject.kind ||
            !sameRef(observation.checkRef, action.checkRef) || this.observations.some((o) => o.observationId === observation.observationId)) {
          throw new Error("AUTONOMOUS_OBSERVATION_INTEGRITY")
        }
        this.observations.push(structuredClone(observation))
        return { accepted: true, decisionId, observation: structuredClone(observation) }
      }
      const output = await this.ports.invoke(structuredClone(proposal), pending.controller.signal)
      if (pending.controller.signal.aborted || this.lifecycle === "closed") {
        this.lateResults.push(decisionId)
        return { accepted: false, code: "AUTONOMOUS_STALE_RESULT" }
      }
      canonicalJson(output)
      return { accepted: true, decisionId, output: structuredClone(output) }
    } catch (error) {
      if (pending.controller.signal.aborted) return { accepted: false, code: "AUTONOMOUS_STALE_RESULT" }
      const code = error instanceof Error ? error.message : "AUTONOMOUS_EXECUTION_ERROR"
      if (code === "AUTONOMOUS_OBSERVATION_INTEGRITY" || /MEASUREMENT_(RESPONSE|PROTOCOL)/.test(code)) {
        this.pending.delete(pendingId)
        pending.settle()
        await this.terminate("runtime_fault")
      }
      // Execution failure is feedback, not a repair instruction. Protocol/identity
      // corruption is treated separately by the owning Coordinator integration.
      return { accepted: false, code }
    } finally {
      this.budget.settle(`decision:${decisionId}`, { modelTokens: 0, costMinorUnits: 0 })
      this.pending.delete(pendingId)
      pending.settle()
    }
  }

  async terminate(reason: Exclude<TerminationReason, "requested">): Promise<CompletionRecord> {
    if (this.completion) return structuredClone(this.completion)
    this.terminationRequested = reason
    // Runtime cancellation can interrupt a prior requested drain.
    for (const pending of this.pending.values()) pending.controller.abort(new Error(reason))
    if (this.closing) await this.closing
    if (this.completion) return structuredClone(this.completion)
    return structuredClone((await this.close(reason))!)
  }

  /** Durable publication is part of completion. A provisional requested close
   * may be replaced before any status publisher observes it. */
  recordPersistenceFault(code: string): void {
    if (!this.completion || this.lifecycle !== "closed") throw new Error("AUTONOMOUS_COMPLETION_STATE")
    const detail = "Status persistence failed [" + code + "]"
    this.completion = {
      ...this.completion,
      reason: "runtime_fault",
      assessment: null,
      unresolvedEffects: [...new Set([...this.completion.unresolvedEffects, detail])],
      endedAt: new Date(this.clock()).toISOString(),
    }
  }

  private close(reason: TerminationReason, final?: DecisionProposal): Promise<CompletionRecord | undefined> {
    if (this.completion) return Promise.resolve(this.completion)
    if (this.closing) return this.closing
    this.lifecycle = "closing"
    const drain = final?.action.kind === "finish" && final.action.openWork === "drain"
    if (!drain) for (const item of this.pending.values()) item.controller.abort(new Error(reason))
    this.closing = (async () => {
      let timer: ReturnType<typeof setTimeout> | undefined
      let unresolved: string[] = []
      let cleanup: Promise<string[]> | undefined
      const startCleanup = () => {
        if (!cleanup) {
          cleanup = Promise.resolve().then(() => this.ports.cleanup())
          void cleanup.catch(() => undefined)
        }
        return cleanup
      }
      try {
        if (!drain) startCleanup()
        const cleaned = await Promise.race([
          Promise.all([...this.pending.values()].map((item) => item.settled)).then(startCleanup),
          new Promise<undefined>((resolve) => { timer = setTimeout(() => resolve(undefined), this.setup.cleanupTimeoutMs) }),
        ])
        if (cleaned === undefined) {
          for (const item of this.pending.values()) item.controller.abort(new Error("AUTONOMOUS_CLEANUP_TIMEOUT"))
          // A port may ignore its action signal. Still ask the owning adapter to
          // stop its processes; do not postpone cleanup until that action returns.
          startCleanup()
          unresolved = [...this.pending.keys()].map((id) => `Cleanup not confirmed: ${id}`)
          if (!unresolved.length) unresolved.push("Executor cleanup not confirmed")
          reason = "runtime_fault"
        } else unresolved = cleaned
      } catch {
        unresolved = ["Owned executor cleanup failed"]
        reason = "runtime_fault"
      } finally { if (timer) clearTimeout(timer) }
      if (reason !== "runtime_fault") reason = this.terminationRequested ?? reason
      if (reason === "requested" && this.clock() >= Date.parse(this.setup.limits.deadlineAt)) reason = "deadline_exceeded"
      if (reason === "requested" && final) {
        const checked = admitDecision(final, { ...this.context(final, []), lifecycle: "active" })
        if (!checked.accepted) {
          this.lifecycle = this.questions.length ? "waiting_input" : "active"
          this.closing = undefined
          return undefined
        }
      }
      const gates: GateResult[] = this.setup.gates.map((gate) => evaluateActionGate(gate,
        this.setup.gateEvidence[gate.id], this.observations, this.setup.binding.runId, this.clock()))
      this.completion = {
        schemaVersion: "completion-v1", runId: this.setup.binding.runId, intentRef: structuredClone(this.setup.intent.ref),
        interpretationRef: structuredClone(this.setup.interpretation.ref), reason,
        assessment: reason === "requested" && final?.action.kind === "finish" ? structuredClone(final.action.assessment) : null,
        observationIds: this.observations.map((o) => o.observationId), gates, candidateDispositions: [],
        unresolvedEffects: unresolved, endedAt: new Date(this.clock()).toISOString(),
      }
      this.lifecycle = "closed"
      clearTimeout(this.deadline)
      // This is a notification, not an awaited durable sink: publish() may itself
      // terminate a Run on storage failure and must not deadlock with close().
      this.onClosed?.()
      return this.completion
    })()
    return this.closing
  }

  private async resourceFailure(error: unknown): Promise<void> {
    const code = error instanceof Error ? error.message : ""
    await this.terminate(code.includes("DEADLINE") ? "deadline_exceeded" : code.includes("BUDGET_EXHAUSTED") ? "budget_exhausted" : "runtime_fault")
  }
}
