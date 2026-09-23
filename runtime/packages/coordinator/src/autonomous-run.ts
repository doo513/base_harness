import type {
  AutonomousCandidateSeal, AutonomousCandidateSnapshot, AutonomousPreparationResult, CompletionRecord, DecisionBasis, DecisionProposal, GateResult, Json, ObservationReport,
  RunLifecycle, SubjectRef, CheckSpec, TerminationReason, AutonomousRunSetup, AutonomousRunPorts, AutonomousDecisionResult, AutonomousRunSnapshot, AutonomousClarification, AutonomousIntentRevision,
  AutonomousTaskSnapshot, TaskProposal, ResourceScope, Operation,
} from "@base-harness/domain-contracts"
import {
  admitDecision, assertAutonomousSchema, canonicalJson, evaluateActionGate, parseDecisionProposal, sameRef,
  scopeContains, validateAuthority, type ActionEffect, type DecisionAdmissionContext,
} from "@base-harness/kernel"
import { AutonomousBudget, type ResourceUsage } from "./autonomous-budget"

export type { AutonomousRunSetup, AutonomousRunPorts, AutonomousDecisionResult } from "@base-harness/domain-contracts"

interface PendingAction {
  controller: AbortController
  settled: Promise<void>
  settle(): void
}

interface TaskRuntime extends AutonomousTaskSnapshot {
  controller?: AbortController
  settled?: Promise<void>
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
  private readonly candidates = new Map<string, AutonomousCandidateSnapshot>()
  private readonly lateResults: string[] = []
  private questions: string[] = []
  private questionRevision = 0
  private preparation?: { basis: DecisionBasis; context: Json }
  private completion?: CompletionRecord
  private closing?: Promise<CompletionRecord | undefined>
  private deadline: ReturnType<typeof setTimeout>
  private terminationRequested?: Exclude<TerminationReason, "requested">
  private readonly unresolvedEffects = new Set<string>()
  private readonly tasks = new Map<string, TaskRuntime>()
  private readonly taskSessions = new Map<string, string>()
  private graphRevision = 1
  private taskSequence = 0
  private readonly activeTaskExecutions = new Set<string>()

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
    const rootCapabilities = [...new Set(setup.authority.capabilities.map((item) => item.operation))]
    const rootScopes = [...new Map(setup.authority.capabilities.flatMap((item) => item.targets)
      .map((scope) => [`${scope.kind}:${scope.selector}`, scope] as const)).values()]
    this.tasks.set(setup.taskId, {
      taskId: setup.taskId, clientTaskKey: "root", revision: 1, depth: 0, state: "running",
      objective: setup.intent.requirements.map((item) => item.text).join("\n") || setup.interpretation.goalSummary,
      requestedCapabilities: rootCapabilities, requestedScopes: rootScopes, dependsOn: [], candidateIds: [],
    })
    this.taskSessions.set(setup.taskId, setup.taskId)
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

  basis(taskId = this.setup.taskId): DecisionBasis {
    const task = this.tasks.get(taskId)
    if (!task) throw new Error("AUTONOMOUS_TASK_UNKNOWN")
    return { runId: this.setup.binding.runId, taskId, taskRevision: task.revision,
      intentRef: structuredClone(this.setup.intent.ref), interpretationRef: structuredClone(this.setup.interpretation.ref),
      authorityRef: structuredClone(this.setup.authority.ref) }
  }

  basisForSession(sessionId: string): DecisionBasis {
    const taskId = this.taskSessions.get(sessionId)
    if (!taskId) throw new Error("AUTONOMOUS_TASK_SESSION_UNKNOWN")
    return this.basis(taskId)
  }

  bindTaskSession(taskId: string, sessionId: string): void {
    const task = this.tasks.get(taskId)
    if (!task || taskId === this.setup.taskId || task.state !== "running" || !sessionId.trim()) {
      throw new Error("AUTONOMOUS_TASK_SESSION_BINDING")
    }
    const existing = task.sessionId
    if (existing && existing !== sessionId) throw new Error("AUTONOMOUS_TASK_SESSION_CONFLICT")
    const bound = this.taskSessions.get(sessionId)
    if (bound && bound !== taskId) throw new Error("AUTONOMOUS_TASK_SESSION_CONFLICT")
    task.sessionId = sessionId
    this.taskSessions.set(sessionId, taskId)
  }

  snapshot(): AutonomousRunSnapshot {
    return structuredClone({ semantics: "autonomous-v1" as const, lifecycle: this.lifecycle, binding: this.setup.binding,
      intent: this.setup.intent, interpretation: this.setup.interpretation, authority: this.setup.authority,
      ...(this.preparation ? { preparation: this.preparation } : {}),
      observations: this.observations, candidates: [...this.candidates.values()],
      tasks: [...this.tasks.values()].map(({ controller: _controller, settled: _settled, ...task }) => task), graphRevision: this.graphRevision,
      questions: this.questions, questionRevision: this.questionRevision, completion: this.completion,
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

  private task(taskId: string): TaskRuntime {
    const task = this.tasks.get(taskId)
    if (!task) throw new Error("AUTONOMOUS_TASK_UNKNOWN")
    return task
  }

  private taskAllows(task: TaskRuntime, effects: readonly ActionEffect[]): boolean {
    return effects.every((effect) => task.requestedCapabilities.includes(effect.operation) &&
      effect.targets.every((target) => task.requestedScopes.some((scope) => scopeContains(scope, target))))
  }

  private normalizeTask(parent: TaskRuntime, proposal: TaskProposal): Omit<TaskRuntime, "taskId"> {
    if (!proposal.requestedCapabilities.length || new Set(proposal.requestedCapabilities).size !== proposal.requestedCapabilities.length ||
        proposal.requestedCapabilities.some((operation) => !parent.requestedCapabilities.includes(operation))) {
      throw new Error("AUTONOMOUS_TASK_CAPABILITY_ESCALATION")
    }
    const scopes = proposal.requestedScopes?.length ? proposal.requestedScopes : parent.requestedScopes
    if (!scopes.length || scopes.some((scope) => !parent.requestedScopes.some((allowed) => scopeContains(allowed, scope)))) {
      throw new Error("AUTONOMOUS_TASK_SCOPE_ESCALATION")
    }
    if (parent.depth + 1 > this.setup.limits.maxTaskDepth) throw new Error("AUTONOMOUS_TASK_DEPTH_EXCEEDED")
    return {
      parentTaskId: parent.taskId, clientTaskKey: proposal.clientTaskKey, revision: 1, depth: parent.depth + 1,
      state: "pending", objective: proposal.objective, requestedCapabilities: [...proposal.requestedCapabilities],
      requestedScopes: structuredClone(scopes), dependsOn: structuredClone(proposal.dependsOn), candidateIds: [],
    }
  }

  private allocateTasks(parent: TaskRuntime, proposals: readonly TaskProposal[]): TaskRuntime[] {
    if (!proposals.length || this.tasks.size + proposals.length > this.setup.limits.maxTotalTasks) {
      throw new Error("AUTONOMOUS_TASK_LIMIT_EXCEEDED")
    }
    const keys = new Set<string>()
    const staged = proposals.map((proposal) => {
      if (keys.has(proposal.clientTaskKey) || [...this.tasks.values()].some((task) =>
        task.parentTaskId === parent.taskId && task.clientTaskKey === proposal.clientTaskKey)) {
        throw new Error("AUTONOMOUS_TASK_KEY_CONFLICT")
      }
      keys.add(proposal.clientTaskKey)
      const normalized = this.normalizeTask(parent, proposal)
      for (const dependency of proposal.dependsOn) {
        const target = this.tasks.get(dependency.taskId)
        if (!target || target.taskId === parent.taskId || target.depth > parent.depth + 1) {
          throw new Error("AUTONOMOUS_TASK_DEPENDENCY_INVALID")
        }
      }
      const taskId = `task:${this.setup.binding.runId}:${++this.taskSequence}`
      return { taskId, ...normalized }
    })
    for (const task of staged) this.tasks.set(task.taskId, task)
    this.graphRevision++
    return staged
  }

  private dependencyMet(dependency: TaskProposal["dependsOn"][number]): boolean {
    const task = this.tasks.get(dependency.taskId)
    if (!task) return false
    if (dependency.when === "settled") return task.state === "settled"
    const candidates = task.candidateIds.map((id) => this.candidates.get(id)).filter(Boolean)
    return dependency.when === "artifact_produced"
      ? candidates.length > 0
      : candidates.some((candidate) => candidate?.state === "applied")
  }

  private taskJson(task: TaskRuntime): Json {
    const { controller: _controller, settled: _settled, ...snapshot } = task
    return JSON.parse(canonicalJson(snapshot)) as Json
  }

  private dispatchTasks(releasedTaskId?: string): Promise<void>[] {
    if (!this.ports.executeTask) return []
    const capacity = this.setup.limits.maxParallelTasks - this.activeTaskExecutions.size +
      (releasedTaskId && this.activeTaskExecutions.has(releasedTaskId) ? 1 : 0)
    if (capacity <= 0) return []
    const runnable = [...this.tasks.values()].filter((task) => task.state === "pending" &&
      task.dependsOn.every((dependency) => this.dependencyMet(dependency))).slice(0, capacity)
    return runnable.map((task) => {
      task.state = "running"
      const controller = new AbortController()
      task.controller = controller
      this.activeTaskExecutions.add(task.taskId)
      const parentTaskId = task.parentTaskId!
      const proposal: TaskProposal = {
        clientTaskKey: task.clientTaskKey, objective: task.objective,
        requestedCapabilities: [...task.requestedCapabilities], requestedScopes: structuredClone(task.requestedScopes),
        dependsOn: structuredClone(task.dependsOn),
      }
      const settled = Promise.resolve().then(() => this.ports.executeTask!({
        taskId: task.taskId, parentTaskId, proposal, requestedScopes: structuredClone(task.requestedScopes), signal: controller.signal,
      })).then((result) => {
        if (controller.signal.aborted || this.lifecycle === "closed") {
          task.state = "cancelled"
          task.error = "AUTONOMOUS_STALE_RESULT"
          this.lateResults.push(task.taskId)
          return
        }
        canonicalJson(result.output)
        task.output = structuredClone(result.output)
        if (result.sessionId) this.bindTaskSession(task.taskId, result.sessionId)
        task.state = "settled"
      }, (error) => {
        task.state = controller.signal.aborted ? "cancelled" : "faulted"
        task.error = error instanceof Error ? error.message : "AUTONOMOUS_TASK_EXECUTION_ERROR"
      }).finally(() => {
        this.activeTaskExecutions.delete(task.taskId)
        task.controller = undefined
        void Promise.all(this.dispatchTasks())
      })
      task.settled = settled
      return settled
    })
  }

  /** Authenticated Host refresh. A revision invalidates every outstanding
   * permit; actors must obtain a new basis and old Candidate receipts stay old. */
  async reviseAuthority(authority: import("@base-harness/domain-contracts").AuthorityGrant): Promise<void> {
    if (!["active", "waiting_input", "preparing"].includes(this.lifecycle)) throw new Error("AUTONOMOUS_AUTHORITY_REVISION_STATE")
    validateAuthority(authority, this.setup.binding.runId, this.clock())
    const current = this.setup.authority
    if (authority.ref.id !== current.ref.id || authority.ref.revision !== current.ref.revision + 1) {
      throw new Error("AUTONOMOUS_AUTHORITY_REVISION")
    }
    for (const item of this.pending.values()) item.controller.abort(new Error("AUTONOMOUS_AUTHORITY_REVISED"))
    await this.ports.reviseAuthority?.(structuredClone(authority))
    this.setup.authority = structuredClone(authority)
    this.setup.binding.authorityRef = structuredClone(authority.ref)
    this.preparation = undefined
  }

  private recordCandidate(value: AutonomousCandidateSeal): AutonomousCandidateSnapshot {
    assertAutonomousSchema("subject", value.candidate)
    const receipt = value.receipt
    const digest = (input: unknown) => typeof input === "string" && /^[a-f0-9]{64}$/.test(input)
    const owner = this.tasks.get(value.taskId)
    if (value.candidate.kind !== "candidate" || !owner || !["running", "settled"].includes(owner.state) || !receipt.receiptId.trim() ||
        receipt.runId !== this.setup.binding.runId || !sameRef(receipt.authorityRef, this.setup.authority.ref) ||
        receipt.candidate.kind !== "candidate" || !sameRef(receipt.candidate, value.candidate) ||
        !digest(receipt.baselineHash) || !digest(receipt.patchHash) || !Array.isArray(value.files) ||
        value.files.some((item) => !item.path.trim() ||
          (item.beforeHash !== null && !digest(item.beforeHash)) || (item.afterHash !== null && !digest(item.afterHash)))) {
      throw new Error("AUTONOMOUS_CANDIDATE_INTEGRITY")
    }
    if (!this.setup.subjects.some((subject) => subject.kind === "candidate" && sameRef(subject, value.candidate))) {
      throw new Error("AUTONOMOUS_CANDIDATE_SUBJECT")
    }
    if (this.candidates.has(value.candidate.id)) throw new Error("AUTONOMOUS_CANDIDATE_DUPLICATE")
    const snapshot: AutonomousCandidateSnapshot = { ...structuredClone(value), state: "sealed" }
    for (const current of this.candidates.values()) {
      if (current.taskId === value.taskId && ["editing", "sealed", "retained"].includes(current.state)) {
        current.state = "discarded"
        current.supersededBy = structuredClone(value.candidate)
      }
    }
    this.candidates.set(value.candidate.id, snapshot)
    owner.candidateIds.push(value.candidate.id)
    void Promise.all(this.dispatchTasks())
    return snapshot
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
    const gateEvidence = structuredClone(this.setup.gateEvidence)
    if (proposal.action.kind === "apply_candidate") {
      for (const gate of this.setup.gates) {
        if (gate.action === "apply_candidate" && gateEvidence[gate.id]) {
          gateEvidence[gate.id]!.subject = structuredClone(proposal.action.candidate)
        }
      }
    }
    return { basis: this.basis(proposal.basis.taskId), lifecycle: this.lifecycle, now: this.clock(), authority: this.setup.authority,
      observations: this.observations, subjects: this.setup.subjects, checks: this.setup.checks, gates: this.setup.gates,
      gateEvidence, supportedActions: ["invoke", "measure", "delegate", "amend_tasks", "ask", "revise_interpretation", "apply_candidate", "finish"],
      resolvedAction: { canonicalAction: canonicalJson(proposal.action), effects } }
  }

  private async execute(proposal: DecisionProposal): Promise<AutonomousDecisionResult> {
    const { action, decisionId } = proposal
    const actor = this.tasks.get(proposal.basis.taskId)
    if (!actor || !["running", "waiting_input"].includes(actor.state)) {
      return { accepted: false, code: "AUTONOMOUS_TASK_NOT_ACTIVE" }
    }
    // Reject stale state before effect resolution (which may consult adapter metadata).
    const initial = admitDecision(proposal, this.context(proposal, []))
    if (!initial.accepted && initial.code !== "AUTONOMOUS_EFFECT_INCOMPLETE") return initial
    let effects: ActionEffect[]
    try {
      effects = action.kind === "delegate"
        ? action.tasks.flatMap((task) => {
            const scopes = task.requestedScopes?.length ? task.requestedScopes : actor.requestedScopes
            return [{ operation: "delegate" as const, targets: structuredClone(scopes) }]
          })
        : action.kind === "amend_tasks"
          ? [{ operation: "delegate" as const, targets: structuredClone(actor.requestedScopes) }]
        : ["invoke", "measure", "apply_candidate"].includes(action.kind)
          ? await this.ports.resolveEffects(structuredClone(action)) : []
    }
    catch (error) {
      const message = error instanceof Error ? error.message : "UNKNOWN"
      const code = /^[A-Z0-9_]+$/.test(message) ? message
        : "AUTONOMOUS_EFFECT_RESOLUTION_" + message.toUpperCase().replace(/[^A-Z0-9]+/g, "_").slice(0, 80)
      return { accepted: false, code }
    }
    const admitted = admitDecision(proposal, this.context(proposal, effects))
    if (!admitted.accepted) return admitted
    if (!this.taskAllows(actor, effects)) return { accepted: false, code: "AUTONOMOUS_TASK_SCOPE_FORBIDDEN" }
    if ((action.kind === "delegate" || action.kind === "amend_tasks") && !this.ports.executeTask) {
      return { accepted: false, code: "AUTONOMOUS_DELEGATION_PORT_UNAVAILABLE" }
    }
    if (effects.some((effect) => effect.operation === "mutate") && action.kind === "invoke" &&
        (!this.ports.beginMutation || !this.ports.sealCandidate)) {
      return { accepted: false, code: "AUTONOMOUS_CANDIDATE_PORT_UNAVAILABLE" }
    }
    if (action.kind === "apply_candidate" && !this.ports.applyCandidate) {
      return { accepted: false, code: "AUTONOMOUS_CANDIDATE_PORT_UNAVAILABLE" }
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
      if (proposal.basis.taskId !== this.setup.taskId) {
        actor.assessment = structuredClone(action.assessment)
        actor.report = structuredClone(action.report)
        return { accepted: true, decisionId, output: this.taskJson(actor) }
      }
      const completion = await this.close("requested", proposal)
      return completion ? { accepted: true, decisionId, completion: structuredClone(completion) } :
        { accepted: false, code: "FINISH_BASIS_CHANGED" }
    }
    if (action.kind !== "invoke" && action.kind !== "measure" && action.kind !== "apply_candidate" &&
        action.kind !== "delegate" && action.kind !== "amend_tasks") {
      return { accepted: false, code: "AUTONOMOUS_CAPABILITY_UNSUPPORTED" }
    }
    try { this.budget.reserve(`decision:${decisionId}`, proposal, { modelTokens: 0, costMinorUnits: 0 }) }
    catch (error) {
      await this.resourceFailure(error)
      return { accepted: false, code: error instanceof Error ? error.message : "AUTONOMOUS_RESOURCE_FAILURE" }
    }
    const pending = this.newPending()
    const pendingId = `decision:${decisionId}`
    this.pending.set(pendingId, pending)
    const mutating = action.kind === "invoke" && effects.some((effect) => effect.operation === "mutate")
    try {
      if (action.kind === "delegate") {
        let created: TaskRuntime[]
        try { created = this.allocateTasks(actor, action.tasks) }
        catch (error) { return { accepted: false, code: error instanceof Error ? error.message : "AUTONOMOUS_TASK_INVALID" } }
        const started = this.dispatchTasks(actor.taskId)
        await Promise.all(started)
        return { accepted: true, decisionId, output: JSON.parse(canonicalJson({
          graphRevision: this.graphRevision, tasks: created.map((task) => this.taskJson(task)),
        })) as Json }
      }
      if (action.kind === "amend_tasks") {
        if (action.expectedGraphRevision !== this.graphRevision) return { accepted: false, code: "AUTONOMOUS_GRAPH_REVISION_STALE" }
        if (!action.changes.length) return { accepted: false, code: "AUTONOMOUS_TASK_AMENDMENT_EMPTY" }
        const added: TaskRuntime[] = []
        for (const change of action.changes) {
          if (change.kind === "add") {
            added.push(...this.allocateTasks(actor, [change.task]))
            continue
          }
          const target = this.tasks.get(change.taskId)
          if (!target || target.parentTaskId !== actor.taskId) return { accepted: false, code: "AUTONOMOUS_TASK_OWNERSHIP" }
          if (change.kind === "replace_pending") {
            if (target.state !== "pending") return { accepted: false, code: "AUTONOMOUS_TASK_RUNNING_REPLACE" }
            if ([...this.tasks.values()].some((task) =>
              task.taskId !== target.taskId && task.parentTaskId === actor.taskId && task.clientTaskKey === change.task.clientTaskKey)) {
              return { accepted: false, code: "AUTONOMOUS_TASK_KEY_CONFLICT" }
            }
            for (const dependency of change.task.dependsOn) {
              const depTarget = this.tasks.get(dependency.taskId)
              if (!depTarget || depTarget.taskId === actor.taskId || depTarget.depth > actor.depth + 1) {
                return { accepted: false, code: "AUTONOMOUS_TASK_DEPENDENCY_INVALID" }
              }
            }
            let replacement: Omit<TaskRuntime, "taskId">
            try { replacement = this.normalizeTask(actor, change.task) }
            catch (error) { return { accepted: false, code: error instanceof Error ? error.message : "AUTONOMOUS_TASK_INVALID" } }
            Object.assign(target, replacement, { taskId: target.taskId, revision: target.revision + 1 })
            this.graphRevision++
          } else {
            if (["settled", "cancelled", "faulted"].includes(target.state)) continue
            target.controller?.abort(new Error("AUTONOMOUS_TASK_CANCELLED"))
            if (target.settled) await target.settled
            target.state = "cancelled"
            this.graphRevision++
          }
        }
        const started = this.dispatchTasks(actor.taskId)
        await Promise.all(started)
        return { accepted: true, decisionId, output: JSON.parse(canonicalJson({
          graphRevision: this.graphRevision,
          tasks: [...this.tasks.values()].filter((task) => task.parentTaskId === actor.taskId).map((task) => this.taskJson(task)),
        })) as Json }
      }
      // Admission and dispatch are synchronous up to the call. No actor-created
      // permit is accepted, and a concurrent cancel invalidates this owned signal.
      if (action.kind === "apply_candidate") {
        const candidate = this.candidates.get(action.candidate.id)
        if (!candidate || candidate.state !== "sealed" || !sameRef(candidate.candidate, action.candidate)) {
          return { accepted: false, code: "AUTONOMOUS_CANDIDATE_STALE" }
        }
        candidate.state = "applying"
        let applied
        try { applied = await this.ports.applyCandidate!(structuredClone(proposal), structuredClone(candidate.receipt), pending.controller.signal) }
        catch (error) {
          const code = error instanceof Error ? error.message : "AUTONOMOUS_CANDIDATE_APPLY_FAILED"
          candidate.state = code.includes("ROLLBACK_INCOMPLETE") ? "recovery_required" : "retained"
          if (candidate.state === "recovery_required") {
            this.pending.delete(pendingId)
            pending.settle()
            await this.terminate("runtime_fault")
          }
          return { accepted: false, code }
        }
        if (applied.candidate.kind !== "candidate" || !sameRef(applied.candidate, candidate.candidate) ||
            !["applied", "recovery_required"].includes(applied.state) || !Array.isArray(applied.unresolvedEffects)) {
          throw new Error("AUTONOMOUS_CANDIDATE_APPLY_PROTOCOL")
        }
        for (const effect of applied.unresolvedEffects) this.unresolvedEffects.add(effect)
        if (applied.journalPath !== undefined) candidate.journalPath = applied.journalPath
        if (pending.controller.signal.aborted || this.lifecycle === "closed") {
          this.lateResults.push(decisionId)
          candidate.state = "recovery_required"
          return { accepted: false, code: "AUTONOMOUS_STALE_RESULT" }
        }
        candidate.state = applied.state
        if (applied.state === "recovery_required") {
          this.pending.delete(pendingId)
          pending.settle()
          await this.terminate("runtime_fault")
          return { accepted: false, code: "AUTONOMOUS_CANDIDATE_RECOVERY_REQUIRED" }
        }
        void Promise.all(this.dispatchTasks())
        return { accepted: true, decisionId, output: JSON.parse(canonicalJson({ candidate: candidate.candidate, state: "applied" })) as Json }
      }
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
      if (mutating) await this.ports.beginMutation!(structuredClone(proposal), pending.controller.signal)
      const output = await this.ports.invoke(structuredClone(proposal), pending.controller.signal)
      if (pending.controller.signal.aborted || this.lifecycle === "closed") {
        this.lateResults.push(decisionId)
        return { accepted: false, code: "AUTONOMOUS_STALE_RESULT" }
      }
      canonicalJson(output)
      if (!mutating) return { accepted: true, decisionId, output: structuredClone(output) }
      const sealed = await this.ports.sealCandidate!(structuredClone(proposal), pending.controller.signal)
      if (!sealed) return { accepted: true, decisionId, output: structuredClone(output) }
      const candidate = this.recordCandidate(sealed)
      return { accepted: true, decisionId, output: JSON.parse(canonicalJson({
        result: output, candidate: candidate.candidate, candidateState: candidate.state,
      })) as Json }
    } catch (error) {
      if (mutating && !pending.controller.signal.aborted) {
        try {
          const sealed = await this.ports.sealCandidate!(structuredClone(proposal), pending.controller.signal)
          if (sealed) this.recordCandidate(sealed)
        } catch { /* Preserve the original execution diagnosis; Workspace state remains retained by cleanup. */ }
      }
      if (pending.controller.signal.aborted) return { accepted: false, code: "AUTONOMOUS_STALE_RESULT" }
      const code = error instanceof Error ? error.message : "AUTONOMOUS_EXECUTION_ERROR"
      if (code === "AUTONOMOUS_OBSERVATION_INTEGRITY" || code === "AUTONOMOUS_CANDIDATE_APPLY_PROTOCOL" ||
          /MEASUREMENT_(RESPONSE|PROTOCOL)/.test(code)) {
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
    const candidateBasis = canonicalJson([...this.candidates.values()].map((item) => ({ candidate: item.candidate, state: item.state })))
    if (!drain) {
      for (const item of this.pending.values()) item.controller.abort(new Error(reason))
      for (const task of this.tasks.values()) if (task.taskId !== this.setup.taskId && !["settled", "cancelled", "faulted"].includes(task.state)) {
        task.controller?.abort(new Error(reason))
        if (!task.controller) task.state = "cancelled"
      }
    }
    this.closing = (async () => {
      let timer: ReturnType<typeof setTimeout> | undefined
      let unresolved: string[] = [...this.unresolvedEffects]
      let cleanup: Promise<string[]> | undefined
      const startCleanup = () => {
        if (!cleanup) {
          cleanup = Promise.resolve().then(() => this.ports.cleanup())
          void cleanup.catch(() => undefined)
        }
        return cleanup
      }
      try {
        if (drain) {
          this.dispatchTasks()
          for (const task of this.tasks.values()) {
            if (task.taskId !== this.setup.taskId && task.state === "pending") {
              task.state = "cancelled"
              unresolved.push(`Task dependency was not settled: ${task.taskId}`)
            }
          }
        }
        if (!drain) startCleanup()
        const cleaned = await Promise.race([
          Promise.all([
            ...[...this.pending.values()].map((item) => item.settled),
            ...[...this.tasks.values()].flatMap((task) => task.settled ? [task.settled] : []),
          ]).then(startCleanup),
          new Promise<undefined>((resolve) => { timer = setTimeout(() => resolve(undefined), this.setup.cleanupTimeoutMs) }),
        ])
        if (cleaned === undefined) {
          for (const item of this.pending.values()) item.controller.abort(new Error("AUTONOMOUS_CLEANUP_TIMEOUT"))
          // A port may ignore its action signal. Still ask the owning adapter to
          // stop its processes; do not postpone cleanup until that action returns.
          startCleanup()
          const pendingEffects = [...this.pending.keys()].map((id) => `Cleanup not confirmed: ${id}`)
          if (!pendingEffects.length) pendingEffects.push("Executor cleanup not confirmed")
          unresolved = [...new Set([...unresolved, ...pendingEffects])]
          reason = "runtime_fault"
        } else unresolved = [...new Set([...unresolved, ...cleaned])]
      } catch {
        unresolved = [...new Set([...unresolved, "Owned executor cleanup failed"])]
        reason = "runtime_fault"
      } finally { if (timer) clearTimeout(timer) }
      if (reason !== "runtime_fault") reason = this.terminationRequested ?? reason
      if (reason === "requested" && this.clock() >= Date.parse(this.setup.limits.deadlineAt)) reason = "deadline_exceeded"
      if (reason === "requested" && final) {
        const currentCandidates = canonicalJson([...this.candidates.values()].map((item) => ({ candidate: item.candidate, state: item.state })))
        if (currentCandidates !== candidateBasis) {
          this.lifecycle = this.questions.length ? "waiting_input" : "active"
          this.closing = undefined
          return undefined
        }
        const checked = admitDecision(final, { ...this.context(final, []), lifecycle: "active" })
        if (!checked.accepted) {
          this.lifecycle = this.questions.length ? "waiting_input" : "active"
          this.closing = undefined
          return undefined
        }
      }
      const gates: GateResult[] = this.setup.gates.map((gate) => evaluateActionGate(gate,
        this.setup.gateEvidence[gate.id], this.observations, this.setup.binding.runId, this.clock()))
      const candidateDispositions = [...this.candidates.values()].map((candidate) => {
        const state = candidate.state === "applied" || candidate.state === "discarded" || candidate.state === "recovery_required"
          ? candidate.state
          : candidate.state === "applying" ? "recovery_required" as const : "retained" as const
        candidate.state = state
        return { candidate: structuredClone(candidate.candidate), state }
      })
      const rootTask = this.tasks.get(this.setup.taskId)
      if (rootTask) rootTask.state = reason === "requested" ? "settled"
        : reason === "cancelled" || reason === "interrupted" ? "cancelled" : "faulted"
      this.completion = {
        schemaVersion: "completion-v1", runId: this.setup.binding.runId, intentRef: structuredClone(this.setup.intent.ref),
        interpretationRef: structuredClone(this.setup.interpretation.ref), reason,
        assessment: reason === "requested" && final?.action.kind === "finish" ? structuredClone(final.action.assessment) : null,
        observationIds: this.observations.map((o) => o.observationId), gates, candidateDispositions,
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
