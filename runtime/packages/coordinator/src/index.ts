import { createHash, randomUUID } from "node:crypto"
import { AsyncLocalStorage } from "node:async_hooks"
import * as Orchestration from "@base-harness/workspace/orchestration"
import {
  createFailureEnvelope,
  failureFingerprint,
  isTrustedFailureEnvelope,
  type TrustedFailureEnvelope,
  createVerificationClient,
  VerificationClientError,
  goalSource,
  materializeProposal,
  type GoalContractProposal,
  type ProcessVerificationClient,
  type VerificationProfile,
  type VerificationStatus,
} from "@base-harness/verification"
import { CandidateService } from "./candidate-service"
import type {
  BeginRunInput,
  PlanExecutionInput,
  RestoredPlanExecutionInput,
  ExecutionPlanLink,
  CoordinatorService,
  CoordinatorWorkerStatus,
  HarnessStatus,
  HostActionEvent,
  IntegrationExecutor,
  StatusPublisher,
  VerificationTarget,
  WorkerExecutor,
  WorkerState,
} from "./contracts"
import { integrationRepairPrompt, workerRepairPrompt } from "./repair-router"
import { PersistenceGateway } from "./persistence-gateway"
import { RunRepository } from "./run-repository"
import { dependenciesComplete, hasPendingWork, nextRunnable } from "./scheduler"
import { inactiveVerification, nonRepairableFailure } from "./state-machine"

type WorkerRecord = CoordinatorWorkerStatus & {
  unit: Orchestration.WorkUnit
  verification?: VerificationStatus
}

type RunRecord = {
  sessionID: string
  runId: string
  goal: string
  workspace: string
  source: ReturnType<typeof goalSource>
  verifier?: ProcessVerificationClient
  verifierFailure?: Error
  verification: VerificationStatus
  workers: Map<string, WorkerRecord>
  context?: unknown
  draining: boolean
  drainRequested: boolean
  executionFailures: Map<string, VerificationStatus>
  metaReviewFailure?: VerificationStatus
  active: Set<string>
  openedScopes: Set<string>
  observedActions: Set<string>
  pendingHostEvents: Array<{ type: string; data: unknown }>
  hostEvents: Promise<void>
  hostEventDepth: number
  maxParallel: number
  interrupted: boolean
  execution: AbortController
  trigger: "auto" | "manual"
  contractAccepted: boolean
  contractProposal?: GoalContractProposal
  executionPlan?: ExecutionPlanLink
  revisesPlan?: ExecutionPlanLink
  planExecutionStarting?: boolean
  graph?: Orchestration.WorkGraph
  integrationStarted: boolean
  integrationComplete: boolean
  rootExecutionFailure?: VerificationStatus
  settledWaiters: Set<() => void>
  rootVerification?: Promise<HarnessStatus>
  publication?: Promise<void>
  persistenceFailed?: boolean
  configuredProfile: VerificationProfile
  effectiveProfile: VerificationProfile
  isolation?: import("./contracts").IsolationStatus
  sandboxRuns: number
}

const record = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === "object" ? (value as Record<string, unknown>) : undefined

const stringValue = (value: unknown) => (typeof value === "string" ? value : undefined)

const artifactPaths = (references: readonly unknown[]) => references.flatMap((reference) => {
  const value = typeof reference === "string" ? reference : stringValue(record(reference)?.path)
  return value ? [value] : []
})

const scopedFailureDetails = (failure: VerificationStatus | undefined) => failure ? {
  failureKind: failure.failureKind,
  failedCriterion: failure.failedCriterion,
  missingEvidence: failure.missingEvidence ?? [],
  repairScope: failure.repairScope,
  repairScopeId: failure.repairScopeId,
  repairCount: failure.repairCount ?? 0,
  failureFingerprint: failure.failureFingerprint,
  message: failure.message,
} : {}

export class CoordinatorRuntime implements CoordinatorService {
  private readonly repository: RunRepository<RunRecord>
  private readonly candidates: CandidateService
  private readonly persistence: PersistenceGateway
  private executor?: WorkerExecutor
  private integrationExecutor?: IntegrationExecutor
  private readonly continuation = new AsyncLocalStorage<{ run: RunRecord; active: boolean }>()
  private completionGate: (sessionID: string) => boolean = () => true
  private readonly publishers = new Set<StatusPublisher>()
  private statusCheckpoint?: (status: HarnessStatus) => Promise<void>
  private readonly revisionTransitions = new Set<string>()

  constructor(
    private readonly verifierFactory: typeof createVerificationClient = createVerificationClient,
    options: {
      repository?: RunRepository<RunRecord>
      candidates?: CandidateService
      persistence?: PersistenceGateway
    } = {},
  ) {
    this.repository = options.repository ?? new RunRepository({ persistent: verifierFactory === createVerificationClient })
    this.candidates = options.candidates ?? new CandidateService()
    this.persistence = options.persistence ?? new PersistenceGateway()
  }

  get orchestration() {
    return this.candidates.api
  }

  private get runs() {
    return this.repository.runs
  }

  private get scopeRoots() {
    return this.repository.scopeRoots
  }

  /** Host-owned artifacts share the same run-scoped redactor as Coordinator persistence. */
  redactForPersistence<T>(runId: string, value: T): T {
    return this.persistence.redact(runId, value)
  }

  registerCompletionGate(gate: (sessionID: string) => boolean) {
    this.completionGate = gate
  }

  /** Durable Host state must settle before any completion event is delivered. */
  registerStatusCheckpoint(checkpoint: (status: HarnessStatus) => Promise<void>) {
    this.statusCheckpoint = checkpoint
  }

  beginPlanning(sessionID: string) {
    const run = this.runFor(sessionID)
    if (!run?.contractAccepted) throw new Error("CONTRACT_REQUIRED: planning requires an accepted contract")
    this.orchestration.beginPlanning(run.sessionID)
  }

  beginDirect(sessionID: string) {
    this.orchestration.beginDirectExecution(sessionID)
  }

  registerWorkerExecutor(executor: WorkerExecutor) {
    this.executor = executor
  }

  registerIntegrationExecutor(executor: IntegrationExecutor) {
    this.integrationExecutor = executor
  }

  isInternalContinuation(sessionID: string) {
    const lease = this.continuation.getStore()
    return lease?.active === true && lease.run.sessionID === sessionID && this.isLive(lease.run)
  }

  private async continueRoot(run: RunRecord, input: Omit<Parameters<IntegrationExecutor>[0], "signal">) {
    if (!this.integrationExecutor || !this.isLive(run)) throw new Error("ROOT_CONTINUATION_UNAVAILABLE")
    const lease = { run, active: true }
    try {
      return await this.continuation.run(lease, () => this.integrationExecutor!({ ...input, signal: run.execution.signal }))
    } finally {
      // Detached async work cannot retain continuation authority after this executor returns.
      lease.active = false
    }
  }

  subscribe(publisher: StatusPublisher) {
    this.publishers.add(publisher)
    return () => this.publishers.delete(publisher)
  }

  beginRun(input: BeginRunInput) {
    return this.openRun(input)
  }

  observe(event: HostActionEvent) {
    return this.observeHostEvent(event.type, event.data)
  }

  async reportMetaReviewFailure(
    sessionID: string,
    error: unknown,
    phase: string,
    source: "harness" | "model" | "tool" = "harness",
  ) {
    const run = this.runFor(sessionID)
    if (!run || !this.isLive(run)) return this.snapshotOrInactive(sessionID)
    if (run.metaReviewFailure) return this.snapshot(run)
    const failure = createFailureEnvelope({
      runId: run.runId, scopeId: run.sessionID, phase: "meta_review." + phase, source,
      producer: source === "model" ? "model_gateway" : source === "tool" ? "tool_host" : "orchestrator",
      error,
    })
    run.metaReviewFailure = this.failureStatus(run, failure)
    run.executionFailures.set(run.sessionID, run.metaReviewFailure)
    run.verification = run.metaReviewFailure
    this.orchestration.markOutcome(run.sessionID, "blocked")
    // Meta review has no evidence authority. Record a Host failure, not a verifier observation.
    await this.publish(run)
    return this.snapshot(run)
  }

  submitWorkGraph(input: { sessionID: string; graph: Orchestration.WorkGraph; context: unknown }) {
    return this.acceptWorkGraph(input.sessionID, input.graph, input.context)
  }

  verify(target: VerificationTarget) {
    return this.verifyRoot(target.sessionID, target.reason ?? "manual")
  }

  private runFor(sessionID: string) {
    this.candidates.activate()
    return this.repository.get(sessionID)
  }

  private isCurrent(run: RunRecord) {
    return this.runs.get(run.sessionID) === run
  }

  private isLive(run: RunRecord) {
    return this.isCurrent(run) && !run.interrupted && !run.persistenceFailed
  }

  private acceptVerifierStatus(run: RunRecord, status: VerificationStatus) {
    if (!this.isLive(run) || run.metaReviewFailure || run.planExecutionStarting) return
    if (status.scopeId === run.sessionID) {
      if (run.rootExecutionFailure) return
      if (status.outcome === "ready" && run.graph && !run.integrationComplete) return
      run.verification = status
      return
    }
    const worker = [...run.workers.values()].find(item => item.scopeId === status.scopeId)
    if (worker && status.outcome) worker.verification = status
    // Child verdicts belong to the child. Only aggregate observations cross into root status.
    run.verification = {
      ...run.verification,
      criterionResults: status.criterionResults,
      claimResults: status.claimResults,
      evidenceFamilies: status.evidenceFamilies,
      evidenceRefs: status.evidenceRefs,
      candidateRefs: status.candidateRefs,
      configuredProfile: status.configuredProfile ?? run.verification.configuredProfile,
      effectiveProfile: status.effectiveProfile ?? run.verification.effectiveProfile,
      escalationReasons: status.escalationReasons ?? run.verification.escalationReasons,
      readyEligible: false,
      readyRef: null,
      scopeAttestation: null,
    }
  }

  private failureStatus(run: RunRecord, failure: TrustedFailureEnvelope): VerificationStatus {
    return {
      ...run.verification,
      scopeId: failure.scopeId,
      state: "failure",
      outcome: "failure",
      failureKind: failure.kind,
      failedCriterion: undefined,
      missingEvidence: [],
      repairScope: undefined,
      repairScopeId: failure.scopeId,
      repairCount: 0,
      failureFingerprint: failureFingerprint(failure, "", failure.scopeId),
      message: failure.message,
      readyEligible: false,
      readyRef: null,
      scopeAttestation: null,
    }
  }

  private executionFailure(run: RunRecord, scopeId: string, error: unknown, phase: string): VerificationStatus {
    if (isTrustedFailureEnvelope(error) && error.runId === run.runId && error.scopeId === scopeId) {
      return this.failureStatus(run, error)
    }
    const source = error instanceof Orchestration.OrchestrationError
      ? error.code === "WORKSPACE_CONFLICT" ? "workspace" : "harness"
      : error instanceof VerificationClientError
        ? error.failureKind === "workspace_conflict" ? "workspace" : "verifier"
        : "harness"
    return this.failureStatus(run, createFailureEnvelope({
      runId: run.runId, scopeId, source, producer: "orchestrator", phase, error,
    }))
  }

  private async failWorker(run: RunRecord, worker: WorkerRecord, error: unknown, phase: string, observed = true) {
    if (!this.isLive(run)) return
    const scopeId = worker.scopeId ?? run.sessionID
    const prior = observed ? run.executionFailures.get(scopeId) : undefined
    worker.verification = prior ?? this.executionFailure(run, scopeId, error, phase)
    worker.state = "failed"
    // An executor may throw before its normal finish callback. Release the overlay execution slot.
    if (worker.scopeId) await this.orchestration.finishChild(worker.scopeId, false)
  }

  private async blockRootExecution(run: RunRecord, error: unknown, phase: string) {
    if (!this.isLive(run)) return
    const failure = run.rootExecutionFailure ?? run.executionFailures.get(run.sessionID)
      ?? this.executionFailure(run, run.sessionID, error, phase)
    // Settlement is not successful integration. Only a new run may clear this terminal latch.
    run.rootExecutionFailure = failure
    run.executionFailures.set(run.sessionID, failure)
    run.integrationComplete = false
    run.verification = {
      ...failure, state: "blocked", outcome: "blocked",
      readyEligible: false, readyRef: null, scopeAttestation: null,
    }
    this.orchestration.markOutcome(run.sessionID, "blocked")
    await this.publish(run)
  }

  private async disposeRun(run: RunRecord, interrupt = true) {
    run.interrupted = true
    run.execution.abort()
    if (interrupt) this.orchestration.markInterrupted(run.sessionID)
    for (const resolve of run.settledWaiters) resolve()
    run.settledWaiters.clear()
    await run.verifier?.dispose().catch(() => undefined)
    try {
      await this.orchestration.flushPersistence(run.sessionID)
    } finally {
      this.persistence.closeRun(run.runId)
      this.repository.delete(run)
    }
  }

  private async ensureVerifier(run: RunRecord) {
    if (run.verifier || run.verifierFailure) return run.verifier
    try {
      run.verifier = await this.verifierFactory(
        {
          runId: run.runId,
          scopeId: run.sessionID,
          workspace: run.workspace,
          goalSources: [run.source],
          configuredProfile: run.configuredProfile,
          effectiveProfile: run.effectiveProfile,
        },
        { redactor: (value) => this.persistence.redact(run.runId, value) },
      )
      this.acceptVerifierStatus(run, run.verifier.snapshot())
      run.verifier.subscribe((status) => {
        if (!this.isLive(run)) return
        this.acceptVerifierStatus(run, status)
        void this.publish(run)
      })
      return run.verifier
    } catch (error) {
      run.verifierFailure = error instanceof Error ? error : new Error(String(error))
      run.verification = {
        ...run.verification,
        state: "failure",
        outcome: "failure",
        failureKind: "harness_verifier_unavailable",
        message: run.verifierFailure.message,
      }
      return undefined
    }
  }

  async openRun(input: BeginRunInput) {
    if (this.revisionTransitions.has(input.sessionID)) throw new Error("RUN_ACTIVE: a planning revision is opening")
    if (!input.revisesPlan) return this.openRunState(input)
    this.revisionTransitions.add(input.sessionID)
    try {
      return await this.openRunState(input)
    } finally {
      this.revisionTransitions.delete(input.sessionID)
    }
  }

  private async openRunState(input: BeginRunInput) {
    this.candidates.activate()
    await this.repository.initialize()
    let existing = this.runs.get(input.sessionID)
    if (existing?.planExecutionStarting) throw new Error("RUN_ACTIVE: a plan execution handoff is in progress")
    const revision = input.revisesPlan ? structuredClone(input.revisesPlan) : undefined
    if (revision) {
      if (!revision.planningRunId || !revision.planId || !Number.isSafeInteger(revision.planRevision)
          || revision.planRevision < 1 || !/^[a-f0-9]{64}$/.test(revision.goalContractHash)) {
        throw new Error("PLAN_REVISION_INVALID")
      }
      if (existing) {
        if (existing.runId !== revision.planningRunId || existing.workspace !== input.workspace
            || !this.isLive(existing)) throw new Error("PLAN_REVISION_RUN_MISMATCH")
        if (!existing.contractAccepted || !existing.contractProposal || existing.graph || this.pending(existing)
            || existing.metaReviewFailure || existing.rootExecutionFailure || existing.verification.outcome) {
          throw new Error("PLAN_RUN_NOT_REVISABLE")
        }
        const hash = createHash("sha256").update(JSON.stringify(existing.contractProposal)).digest("hex")
        if (hash !== revision.goalContractHash) throw new Error("PLAN_CONTRACT_MISMATCH")
        existing.planExecutionStarting = true
        try {
          await existing.hostEvents
          if (!this.isLive(existing)) throw new Error("PLAN_REVISION_RUN_MISMATCH")
          const archived = this.persistence.redact(existing.runId, {
            ...this.snapshot(existing), phase: "plan_ready" as const, outcome: undefined, readyEligible: false,
          })
          // Revised goals get fresh source provenance, policy and verifier state, not old observations.
          await this.disposeRun(existing)
          await this.repository.persist(archived, false)
        } finally {
          existing.planExecutionStarting = false
        }
        existing = undefined
      }
    }
    if (existing && existing.workspace !== input.workspace) {
      await this.disposeRun(existing)
      existing = undefined
    }
    if (existing && (
      existing.interrupted ||
      (!this.pending(existing) && ["ready", "blocked", "failure"].includes(existing.verification.outcome ?? ""))
    )) {
      await this.disposeRun(existing, false)
      existing = undefined
    }
    if (existing) {
      if (input.context !== undefined) existing.context = input.context
      return this.snapshot(existing)
    }
    const runId = "run-" + randomUUID()
    this.orchestration.beginPrompt({ sessionID: input.sessionID, workspace: input.workspace, goal: input.goal, exploration: "manual" })
    this.orchestration.setRunIdentity(input.sessionID, runId)
    this.persistence.openRun(runId)
    const source = goalSource(input.goal, "session-" + input.sessionID, "user_message")
    const profile = input.configuredProfile ?? "adaptive"
    const run: RunRecord = {
      sessionID: input.sessionID,
      runId,
      goal: input.goal,
      workspace: input.workspace,
      source,
      revisesPlan: revision,
      verification: inactiveVerification(runId, input.sessionID, input.maxSameFailureRepairs),
      workers: new Map(),
      draining: false,
      drainRequested: false,
      executionFailures: new Map(),
      active: new Set(),
      openedScopes: new Set([input.sessionID]),
      observedActions: new Set(),
      pendingHostEvents: [],
      hostEvents: Promise.resolve(),
      hostEventDepth: 0,
      maxParallel: Math.max(1, Math.min(2, input.maxParallelWorkUnits ?? 2)),
      interrupted: false,
      execution: new AbortController(),
      trigger: input.trigger ?? "auto",
      contractAccepted: false,
      context: input.context,
      integrationStarted: false,
      integrationComplete: true,
      settledWaiters: new Set(),
      configuredProfile: profile,
      effectiveProfile: input.effectiveProfile ?? profile,
      sandboxRuns: 0,
    }
    this.repository.set(run)
    await this.publish(run)
    return this.snapshot(run)
  }

  async beginPlanExecution(sessionID: string, input: PlanExecutionInput) {
    const planning = this.runs.get(sessionID)
    if (!planning || !this.isLive(planning) || planning.runId !== input.planningRunId) {
      throw new Error("PLAN_RUN_MISMATCH: the reviewed planning run is no longer active")
    }
    if (planning.planExecutionStarting) throw new Error("RUN_ACTIVE: a plan execution handoff is in progress")
    if (!planning.contractAccepted || !planning.contractProposal || planning.graph || this.pending(planning)
        || planning.metaReviewFailure || planning.rootExecutionFailure || planning.verification.outcome) {
      throw new Error("PLAN_RUN_NOT_EXECUTABLE: only an accepted, unexecuted planning run can be handed off")
    }
    const contract = structuredClone(planning.contractProposal)
    const hash = createHash("sha256").update(JSON.stringify(contract)).digest("hex")
    if (!input.planId.trim() || !Number.isInteger(input.planRevision) || input.planRevision < 1
        || hash !== input.goalContractHash) {
      throw new Error("PLAN_CONTRACT_MISMATCH: execution must use the reviewed contract")
    }
    const link: ExecutionPlanLink = {
      planningRunId: planning.runId, planId: input.planId,
      planRevision: input.planRevision, goalContractHash: input.goalContractHash,
    }
    planning.planExecutionStarting = true
    try {
      await planning.hostEvents
      if (!this.isLive(planning)) throw new Error("PLAN_RUN_MISMATCH: planning was cancelled during handoff")
      const archived = this.persistence.redact(planning.runId, {
        ...this.snapshot(planning), phase: "plan_ready" as const, executionPlan: link,
        outcome: undefined, readyEligible: false,
      })
      const nextInput: BeginRunInput = {
        sessionID, workspace: planning.workspace, goal: planning.goal,
        configuredProfile: planning.configuredProfile, effectiveProfile: planning.effectiveProfile,
        maxSameFailureRepairs: planning.verification.maxSameFailureRepairs,
        maxParallelWorkUnits: planning.maxParallel, trigger: planning.trigger,
        context: input.context ?? planning.context,
      }
      // Closing a planning sidecar cannot transfer its observations, evidence, or completion authority.
      await this.disposeRun(planning)
      await this.repository.persist(archived, false)
      const opened = await this.openRun(nextInput)
      const execution = this.runs.get(sessionID)
      if (!execution || execution.runId === planning.runId || execution.runId !== opened.runId) {
        throw new Error("PLAN_EXECUTION_RUN_INVALID: a fresh execution run is required")
      }
      execution.executionPlan = link
      await this.publish(execution)
      const accepted = await this.proposeContract(sessionID, contract)
      if (!this.isLive(execution) || !execution.contractAccepted
          || ["repair", "blocked", "failure", "needs_input", "repair_exhausted"].includes(accepted.outcome ?? "")) {
        return this.snapshot(execution)
      }
      // A fresh run starts in direct. Restore its reviewed planning phase before WorkGraph dispatch.
      this.beginPlanning(sessionID)
      await this.publish(execution)
      return this.snapshot(execution)
    } finally {
      planning.planExecutionStarting = false
    }
  }

  async beginRestoredPlanExecution(sessionID: string, input: RestoredPlanExecutionInput) {
    if (this.runs.has(sessionID)) throw new Error("RUN_ACTIVE: restoration cannot replace an in-memory run")
    const hash = createHash("sha256").update(JSON.stringify(input.contract)).digest("hex")
    if (!input.planningRunId || !input.planId || !Number.isSafeInteger(input.planRevision) || input.planRevision < 1
        || hash !== input.goalContractHash) throw new Error("PLAN_CONTRACT_MISMATCH")
    const opened = await this.openRun({
      sessionID, workspace: input.workspace, goal: input.goal, context: input.context,
      configuredProfile: input.configuredProfile, effectiveProfile: input.effectiveProfile,
      trigger: input.trigger, maxSameFailureRepairs: input.maxSameFailureRepairs,
      maxParallelWorkUnits: input.maxParallelWorkUnits,
    })
    const run = this.runs.get(sessionID)
    if (!run || run.runId !== opened.runId || run.runId === input.planningRunId) throw new Error("PLAN_EXECUTION_RUN_INVALID")
    run.executionPlan = {
      planningRunId: input.planningRunId, planId: input.planId,
      planRevision: input.planRevision, goalContractHash: input.goalContractHash,
    }
    await this.publish(run)
    const accepted = await this.proposeContract(sessionID, structuredClone(input.contract))
    if (this.isLive(run) && run.contractAccepted
        && !["repair", "blocked", "failure", "needs_input", "repair_exhausted"].includes(accepted.outcome ?? "")) {
      this.beginPlanning(sessionID)
      await this.publish(run)
    }
    return this.snapshot(run)
  }

  async reportPlanExecutionFailure(sessionID: string, error: unknown) {
    const run = this.runFor(sessionID)
    if (!run) return this.snapshotOrInactive(sessionID)
    await this.blockRootExecution(run, error, "plan.execute")
    return this.snapshot(run)
  }

  async proposeContract(sessionID: string, proposal: GoalContractProposal) {
    const run = this.runFor(sessionID)
    if (!run) return this.snapshotOrInactive(sessionID)
    if (run.planExecutionStarting) throw new Error("RUN_ACTIVE: contract changes are suspended during execution handoff")
    if (run.metaReviewFailure) throw new Error("META_REVIEW_RUN_FAILED: start a new run after resolving the review failure")
    await this.ensureVerifier(run)
    if (!run.verifier) return this.snapshot(run)
    const contract = materializeProposal(run.source, proposal)
    run.contractAccepted = false
    this.acceptVerifierStatus(run, await run.verifier.proposeContract(contract))
    const accepted = run.verification.goalContract
    if (
      run.verification.contractStatus !== "accepted" ||
      !accepted ||
      accepted.contractId !== contract.contractId ||
      accepted.revision !== contract.revision ||
      ["repair", "blocked", "failure", "needs_input", "repair_exhausted"].includes(run.verification.outcome ?? "")
    ) {
      await this.publish(run)
      return this.snapshot(run)
    }
    run.contractAccepted = true
    run.contractProposal = structuredClone(proposal)
    this.orchestration.registerContract(run.sessionID, accepted.claims.map((claim) => claim.claimId), accepted.criteria.map((criterion) => criterion.criterionId))
    const pending = run.pendingHostEvents.splice(0)
    for (const event of pending) await this.observeHostEvent(event.type, event.data)
    await this.publish(run)
    return this.snapshot(run)
  }

  async acceptWorkGraph(sessionID: string, graph: Orchestration.WorkGraph, context: unknown) {
    const run = this.runFor(sessionID)
    if (!run) throw new Error("Coordinator run is not open")
    if (run.planExecutionStarting) throw new Error("RUN_ACTIVE: WorkGraph dispatch is suspended during execution handoff")
    if (run.metaReviewFailure) throw new Error("META_REVIEW_RUN_FAILED: WorkGraph dispatch is suspended")
    if (run.rootExecutionFailure) throw new Error("ROOT_EXECUTION_FAILED: start a new run before dispatching more WorkUnits")
    if (!run.contractAccepted) throw new Error("CONTRACT_REQUIRED: WorkGraph requires an accepted GoalContract")
    if (graph.units.length > 64) throw new Error("WorkGraph exceeds the maximum of 64 WorkUnits")
    await this.orchestration.acceptWorkGraph(run.sessionID, graph)
    run.context = context
    run.graph = graph
    run.integrationStarted = false
    run.integrationComplete = false
    run.workers = new Map(
      graph.units.map((unit) => [
        unit.id,
        { workUnitId: unit.id, title: unit.title, state: "queued" as const, repairCount: 0, unit },
      ]),
    )
    await this.publish(run)
    void this.drain(run)
    return this.snapshot(run)
  }

  isManagedWorkGraph(sessionID: string) {
    return (this.runFor(sessionID)?.workers.size ?? 0) > 0
  }

  registerWorkerScope(rootSessionID: string, scopeId: string, workUnitId: string) {
    const run = this.runFor(rootSessionID)
    const worker = run?.workers.get(workUnitId)
    if (!run || !worker) return
    worker.scopeId = scopeId
    this.scopeRoots.set(scopeId, run.sessionID)
    void this.publish(run)
  }

  private dependenciesComplete(run: RunRecord, worker: WorkerRecord) {
    return dependenciesComplete(worker, run.workers)
  }

  private async drain(run: RunRecord) {
    if (!this.isLive(run)) return
    if (run.draining) {
      run.drainRequested = true
      return
    }
    run.draining = true
    try {
      do {
        run.drainRequested = false
        while (this.isLive(run) && run.active.size < run.maxParallel) {
          const next = nextRunnable(run.workers)
          if (!next) break
          if (!this.executor || !run.context) {
            await this.failWorker(run, next, new Error("Coordinator worker executor is unavailable."), "worker.dispatch")
            continue
          }
          next.state = "running"
          run.active.add(next.workUnitId)
          void this.executeWorker(run, next)
        }
        if (this.isLive(run)) this.finalizeScheduling(run)
        await this.publish(run)
      } while (run.drainRequested && this.isLive(run))
    } finally {
      run.draining = false
    }
  }

  private async executeWorker(run: RunRecord, worker: WorkerRecord) {
    let phase = "worker.execute"
    try {
      let taskID: string | undefined
      let repairPrompt: string | undefined
      do {
        if (!this.isLive(run)) return
        if (worker.state === "repairing") {
          phase = "worker.repair.prepare"
          if (!worker.scopeId || !run.verifier) {
            throw new VerificationClientError("harness_verifier_unavailable", "Repair requires the original scope and verifier.")
          }
          repairPrompt = workerRepairPrompt({
            fingerprint: worker.failureFingerprint,
            failedCriterion: worker.verification?.failedCriterion,
            missingEvidence: worker.verification?.missingEvidence,
          })
          // Keep the candidate and overlay intact until the verifier accepts reopening this scope.
          const reopened = await run.verifier.reopenScope(worker.scopeId)
          if (!this.isLive(run)) return
          if (reopened.scopeId !== worker.scopeId || reopened.state === "failure" || reopened.outcome) {
            throw new VerificationClientError("harness_verifier_error", reopened.message ?? "Verifier did not accept scope reopening.")
          }
          this.orchestration.reopenScope(worker.scopeId)
          run.executionFailures.delete(worker.scopeId)
          taskID = worker.scopeId
          worker.state = "running"
        }
        phase = taskID ? "worker.repair.execute" : "worker.execute"
        const result = await this.executor!({
          rootSessionID: run.sessionID, unit: worker.unit, context: run.context, signal: run.execution.signal, taskID, repairPrompt,
        })
        if (!this.isLive(run)) return
        if (worker.scopeId && worker.scopeId !== result.sessionID) {
          throw new Error("WORKER_SCOPE_MISMATCH: executor returned a different child session.")
        }
        worker.scopeId = result.sessionID
        this.scopeRoots.set(result.sessionID, run.sessionID)
        if (!["completed", "failed", "repairing", "repair_exhausted"].includes(worker.state)) {
          throw new Error("WORKER_RESULT_UNVERIFIED: executor returned without candidate verification.")
        }
      } while ((worker.state as WorkerState) === "repairing")
    } catch (error) {
      if ((worker.state as WorkerState) !== "repair_exhausted") {
        await this.failWorker(run, worker, error, phase, phase !== "worker.repair.prepare")
      }
    } finally {
      run.active.delete(worker.workUnitId)
      await this.publish(run)
      if (this.isLive(run)) void this.drain(run)
    }
  }

  async finishWorker(sessionID: string, success: boolean) {
    const owner = this.orchestration.snapshot(sessionID)
    const run = this.runFor(sessionID) ?? (owner ? this.runs.get(owner.sessionID) : undefined)
    if (!run || !this.isLive(run)) return
    const candidate = await this.orchestration.finishChild(sessionID, success)
    if (!this.isLive(run) || (candidate && candidate.runId !== run.runId)) return
    const worker = candidate
      ? run.workers.get(candidate.workUnitId)
      : [...run.workers.values()].find((item) => item.scopeId === sessionID)
    if (!success || !candidate || !worker) {
      // No verified rejection means there is no trusted repair target.
      if (worker) {
        worker.state = "failed"
        worker.verification = run.executionFailures.get(sessionID)
          ?? this.executionFailure(run, sessionID, new Error("Worker ended without a verified candidate."), "worker.finish")
      }
      await this.publish(run)
      return
    }
    await run.hostEvents
    if (!this.isLive(run)) return
    worker.scopeId = sessionID
    worker.state = "candidate_ready"
    this.scopeRoots.set(sessionID, run.sessionID)
    await this.ensureVerifier(run)
    if (!this.isLive(run)) return
    if (!run.verifier) {
      await this.failWorker(run, worker, new VerificationClientError("harness_verifier_unavailable", "Candidate verifier is unavailable."), "candidate.verify", false)
      await this.publish(run)
      return
    }
    try {
      if (!run.openedScopes.has(sessionID)) {
        await run.verifier.openScope(sessionID, run.sessionID, {
          kind: "work_unit",
          assignedClaimIds: worker.unit.claimIds,
        })
        run.openedScopes.add(sessionID)
      }
      if (!this.isLive(run)) return
      const candidateWorkspace = await this.orchestration.materializeCandidate(candidate.candidateId)
      if (!this.isLive(run)) return
      const attachedCandidate = { ...candidate, candidateWorkspace }
      await run.verifier.observe({
        scopeId: sessionID,
        claimIds: worker.unit.claimIds,
        tool: "candidate.patch",
        status: "completed",
        output: attachedCandidate,
      })
      if (!this.isLive(run)) return
      await run.verifier.attachCandidate(attachedCandidate)
      if (!this.isLive(run)) return
      this.orchestration.markCandidateVerifying(candidate.candidateId)
      worker.state = "verifying"
      await this.publish(run)
      const verified = await run.verifier.verify("completion", sessionID, {
        claimIds: worker.unit.claimIds,
        criterionIds: worker.unit.criterionIds,
      })
      if (!this.isLive(run)) return
      worker.verification = verified
      this.acceptVerifierStatus(run, verified)
      if (verified.outcome !== "scope_verified" || !verified.scopeAttestation) {
        worker.repairCount = verified.repairCount ?? worker.repairCount
        worker.failureFingerprint = verified.failureFingerprint
        worker.state =
          verified.outcome === "repair_exhausted"
            ? "repair_exhausted"
            : verified.outcome === "repair" && !nonRepairableFailure(verified.failureKind)
              ? "repairing"
              : "failed"
        if (worker.state === "repairing") await this.orchestration.releaseCandidateWorkspace(candidate.candidateId)
        await this.publish(run)
        return
      }
      worker.state = "committing"
      await this.publish(run)
      if (!this.isLive(run)) return
      const attestation = verified.scopeAttestation
      await this.orchestration.commitCandidate(candidate.candidateId, attestation)
      if (!this.isLive(run)) return
      const committed = await run.verifier.commitCandidate(attestation, sessionID)
      if (committed.state === "failure" || committed.outcome === "failure") {
        throw new VerificationClientError(committed.failureKind ?? "harness_verifier_error", committed.message ?? "Candidate commit was not acknowledged")
      }
      worker.state = "completed"
      await this.publish(run)
    } catch (error) {
      // Preserve the overlay and verification workspace for non-repairable failures.
      await this.failWorker(run, worker, error, "candidate.verify_commit", false)
      await this.publish(run)
    }
  }

  private finalizeScheduling(run: RunRecord) {
    if (!this.isLive(run) || run.active.size > 0) return
    const workers = [...run.workers.values()]
    if (workers.length && workers.every((worker) => worker.state === "completed")) {
      void this.startIntegration(run)
      return
    }
    const runnable = workers.some(
      (worker) => worker.state === "queued" && this.dependenciesComplete(run, worker),
    )
    const terminalFailure = workers.find((worker) => worker.state === "failed" || worker.state === "repair_exhausted")
    if (!runnable && terminalFailure) {
      this.orchestration.markOutcome(run.sessionID, "blocked")
      run.verification = {
        ...run.verification,
        ...scopedFailureDetails(terminalFailure.verification),
        state: "blocked",
        outcome: "blocked",
        readyEligible: false,
        readyRef: null,
        scopeAttestation: null,
        message: terminalFailure.verification?.message ?? run.verification.message
          ?? "No runnable WorkUnit remains for the unresolved required criteria.",
      }
    }
  }

  private async startIntegration(run: RunRecord) {
    if (run.integrationStarted || run.integrationComplete || run.interrupted) return
    run.integrationStarted = true
    await this.publish(run)
    if (!this.integrationExecutor || !run.context || !run.graph) {
      await this.blockRootExecution(run,
        Object.assign(new Error("Coordinator root integration executor is unavailable."), { code: "ROOT_INTEGRATION_UNAVAILABLE" }),
        "root.integration.dispatch")
      return
    }
    try {
      await this.continueRoot(run, {
        rootSessionID: run.sessionID,
        context: run.context,
        integrationPaths: run.graph.integrationPaths,
        integrationRequests: run.graph.units.flatMap((unit) => unit.integrationRequests),
      })
      if (!this.isLive(run)) return
      run.integrationComplete = true
      await this.publish(run)
      if (run.trigger === "auto") await this.verifyRoot(run.sessionID, "automatic")
    } catch (error) {
      if (!this.isLive(run)) return
      await this.blockRootExecution(run, error, "root.integration")
    }
  }

  private pending(run: RunRecord) {
    return hasPendingWork(
      run.workers,
      run.active.size,
      run.integrationStarted,
      run.integrationComplete,
      run.verification.outcome,
    )
  }

  private async waitForSettled(run: RunRecord) {
    while (!run.interrupted && this.pending(run)) {
      await new Promise<void>((resolve) => run.settledWaiters.add(resolve))
    }
  }

  async verifyRoot(sessionID: string, reason: "automatic" | "manual" | "completion" = "manual") {
    const run = this.runFor(sessionID)
    if (!run) return this.snapshotOrInactive(sessionID)
    if (run.interrupted || run.planExecutionStarting || (run.executionPlan && !run.graph)
        || !run.contractAccepted || !this.completionGate(sessionID)) return this.snapshot(run)
    if (reason === "completion") await this.waitForSettled(run)
    if (run.interrupted || !this.completionGate(sessionID)) return this.snapshot(run)
    if (this.pending(run)) return this.snapshot(run)
    if (run.rootExecutionFailure) return this.snapshot(run)
    const requiredClaims = new Set(
      run.verification.goalContract?.criteria.filter(criterion => criterion.required).flatMap(criterion => criterion.claimIds) ?? [],
    )
    const unresolvedWorker = run.graph && [...run.workers.values()].find(worker =>
      worker.state !== "completed" && worker.unit.claimIds.some(claimId => requiredClaims.has(claimId)),
    )
    if (unresolvedWorker) {
      this.orchestration.markOutcome(run.sessionID, "blocked")
      run.verification = {
        ...run.verification, ...scopedFailureDetails(unresolvedWorker.verification),
        state: "blocked", outcome: "blocked", readyEligible: false, readyRef: null, scopeAttestation: null,
        message: unresolvedWorker.verification?.message ?? run.verification.message
          ?? "Unresolved required WorkUnits prevent root completion.",
      }
      await this.publish(run)
      return this.snapshot(run)
    }
    if (run.graph && !run.integrationComplete) {
      await this.blockRootExecution(run,
        Object.assign(new Error("Successful root integration is required before Ready."), { code: "ROOT_INTEGRATION_INCOMPLETE" }),
        "root.verify.integration_gate")
      return this.snapshot(run)
    }
    await this.ensureVerifier(run)
    if (!run.verifier) return this.snapshot(run)
    await run.hostEvents
    if (!this.isLive(run) || run.planExecutionStarting) return this.snapshot(run)
    const rootFailure = run.executionFailures.get(run.sessionID)
    if (rootFailure && nonRepairableFailure(rootFailure.failureKind)) {
      // A synthetic completion observation is not recovery from a provider/verifier failure.
      run.verification = { ...rootFailure, state: "blocked", outcome: "blocked" }
      this.orchestration.markOutcome(run.sessionID, "blocked")
      await this.publish(run)
      return this.snapshot(run)
    }
    if (run.rootVerification) return run.rootVerification
    const verification = (async () => {
      do {
        this.orchestration.requestVerification(run.sessionID)
        const claimIds = run.verification.goalContract?.claims.map((claim) => claim.claimId) ?? []
        await run.verifier!.observe({
          scopeId: run.sessionID,
          claimIds,
          tool: "session.completion",
          status: "completed",
          metadata: { coordinator: true, isolation: run.isolation },
        })
        const verified = await run.verifier!.verify(reason, run.sessionID)
        if (!this.isLive(run)) return this.snapshot(run)
        this.acceptVerifierStatus(run, verified)
        if (run.verification.outcome !== "repair" || nonRepairableFailure(run.verification.failureKind)) break
        if (!this.integrationExecutor || !run.context) {
          await this.blockRootExecution(run,
            Object.assign(new Error("Root repair requires the Coordinator integration executor."), { code: "ROOT_REPAIR_UNAVAILABLE" }),
            "root.repair.dispatch")
          break
        }
        this.orchestration.markOutcome(run.sessionID, "repair")
        run.integrationComplete = false
        await this.publish(run)
        await this.continueRoot(run, {
          rootSessionID: run.sessionID,
          context: run.context,
          integrationPaths: run.graph?.integrationPaths ?? [],
          integrationRequests: run.graph?.units.flatMap((unit) => unit.integrationRequests) ?? [],
          repairPrompt: integrationRepairPrompt({
            fingerprint: run.verification.failureFingerprint,
            failedCriterion: run.verification.failedCriterion,
            missingEvidence: run.verification.missingEvidence,
          }),
        })
        run.integrationComplete = true
        await this.publish(run)
      } while (!run.interrupted)
      if (run.verification.outcome === "ready" || run.verification.outcome === "repair" || run.verification.outcome === "blocked") {
        this.orchestration.markOutcome(run.sessionID, run.verification.outcome === "repair" ? "blocked" : run.verification.outcome)
      } else if (run.verification.outcome === "repair_exhausted") {
        this.orchestration.markOutcome(run.sessionID, "blocked")
      }
      await this.publish(run)
      return this.snapshot(run)
    })()
    run.rootVerification = verification
    try {
      return await verification
    } catch (error) {
      if (!this.isLive(run)) return this.snapshot(run)
      await this.blockRootExecution(run, error, "root.verify")
      return this.snapshot(run)
    } finally {
      if (run.rootVerification === verification) run.rootVerification = undefined
    }
  }

  async observeHostEvent(type: string, data: unknown) {
    const properties = record(data)
    const part = type === "message.part.updated" ? record(properties?.part) : undefined
    const sessionID = stringValue(part?.sessionID) ?? stringValue(properties?.sessionID)
    if (!sessionID) return
    const run = this.runFor(sessionID)
    if (!run || run.interrupted || run.metaReviewFailure) return
    if (!run.contractAccepted) {
      if (type === "session.error" || (type === "message.part.updated" && part?.type === "tool")) {
        if (run.pendingHostEvents.length < 2048) run.pendingHostEvents.push({ type, data })
      }
      return
    }
    await this.ensureVerifier(run)
    if (!run.verifier) return
    if (run.hostEventDepth >= 2048) {
      run.verification = {
        ...run.verification,
        state: "failure",
        outcome: "failure",
        failureKind: "harness_error",
        message: "Coordinator host event queue exceeded 2048 pending events.",
      }
      await this.publish(run)
      return
    }
    run.hostEventDepth += 1
    const previous = run.hostEvents
    let release!: () => void
    run.hostEvents = new Promise<void>((resolve) => {
      release = resolve
    })
    await previous
    try {
      if (!this.isLive(run)) return
      if (type === "message.part.updated" && part?.type === "tool") {
        const state = record(part.state)
        const status = state?.status
        if (status !== "completed" && status !== "error") return
        const actionKey = [sessionID, stringValue(part.id) ?? "tool", status].join(":")
        if (run.observedActions.has(actionKey)) return
        run.observedActions.add(actionKey)
        const worker = [...run.workers.values()].find((item) => item.scopeId === sessionID)
        const claimIds = worker?.unit.claimIds ?? run.verification.goalContract?.claims.map((claim) => claim.claimId) ?? []
        if (sessionID !== run.sessionID && !run.openedScopes.has(sessionID)) {
          await run.verifier.openScope(sessionID, run.sessionID, {
            kind: "work_unit",
            assignedClaimIds: claimIds,
          })
          run.openedScopes.add(sessionID)
        }
        const rawError = state?.error
        const rawFailure = record(rawError)
        const sandboxCode = stringValue(rawFailure?.code)
        const sandboxFailure = sandboxCode?.startsWith("SANDBOX_") || rawFailure?.name === "SandboxError"
        const failure = status === "error"
          ? createFailureEnvelope({
              runId: run.runId,
              scopeId: sessionID,
              actionId: stringValue(part.id),
              source: sandboxFailure ? "harness" : "tool",
              producer: sandboxFailure ? "orchestrator" : "tool_host",
              phase: sandboxFailure ? "sandbox.execute" : "tool.execute",
              error: rawError,
            })
          : undefined
        if (failure) run.executionFailures.set(sessionID, this.failureStatus(run, failure))
        const observed = await run.verifier.observe({
          scopeId: sessionID,
          claimIds,
          tool: stringValue(part.tool) ?? "tool",
          status,
          input: state?.input,
          output: state?.output,
          error: failure,
          metadata: { hostObserved: true, callId: stringValue(part.callID) },
        })
        this.acceptVerifierStatus(run, observed)
        if (status === "completed" && observed.state !== "failure") run.executionFailures.delete(sessionID)
        await this.publish(run)
        return
      }
      if (type === "session.error" && properties?.error) {
        const key = `session.error:${sessionID}:${stringValue(record(properties.error)?.name) ?? "unknown"}`
        if (run.observedActions.has(key)) return
        run.observedActions.add(key)
        const worker = [...run.workers.values()].find((item) => item.scopeId === sessionID)
        const claimIds = worker?.unit.claimIds ?? run.verification.goalContract?.claims.map((claim) => claim.claimId) ?? []
        if (sessionID !== run.sessionID && !run.openedScopes.has(sessionID)) {
          await run.verifier.openScope(sessionID, run.sessionID, {
            kind: "work_unit",
            assignedClaimIds: claimIds,
          })
          run.openedScopes.add(sessionID)
        }
        const failure = createFailureEnvelope({
          runId: run.runId,
          scopeId: sessionID,
          source: "model",
          producer: "model_gateway",
          phase: "model.response",
          error: properties.error,
        })
        run.executionFailures.set(sessionID, this.failureStatus(run, failure))
        this.acceptVerifierStatus(run, await run.verifier.observe({
          scopeId: sessionID,
          claimIds,
          tool: "model",
          status: "error",
          error: failure,
          metadata: { hostObserved: true },
        }))
        await this.publish(run)
        return
      }
      if (
        type === "session.status" &&
        sessionID === run.sessionID &&
        record(properties?.status)?.type === "idle" &&
        run.trigger === "auto" &&
        run.observedActions.size > 0
      ) {
        queueMicrotask(() => void this.verifyRoot(run.sessionID, "automatic"))
      }
    } catch (error) {
      if (!this.isLive(run)) return
      const failure = this.executionFailure(run, sessionID,
        error instanceof VerificationClientError ? error : new VerificationClientError("harness_verifier_error", error instanceof Error ? error.message : String(error)),
        "action.observe")
      run.executionFailures.set(sessionID, failure)
      if (sessionID === run.sessionID) run.verification = failure
      const worker = [...run.workers.values()].find(item => item.scopeId === sessionID)
      if (worker) worker.verification = failure
      await this.publish(run)
    } finally {
      run.hostEventDepth -= 1
      release()
    }
  }

  async cancel(sessionID: string) {
    const run = this.runFor(sessionID)
    if (!run) return this.snapshotOrInactive(sessionID)
    run.interrupted = true
    run.execution.abort()
    run.verification = { ...run.verification, outcome: undefined, readyEligible: false, readyRef: null, scopeAttestation: null }
    this.orchestration.markInterrupted(run.sessionID)
    await run.verifier?.dispose().catch(() => undefined)
    await this.publish(run)
    return this.snapshot(run)
  }

  async closeWorkspace(workspace: string) {
    const matches = [...this.runs.values()].filter((run) => run.workspace === workspace)
    await Promise.all(matches.map((run) => this.disposeRun(run)))
  }

  async recordIsolation(sessionID: string, isolation: import("./contracts").IsolationStatus) {
    const run = this.runFor(sessionID)
    if (!run) return this.snapshotOrInactive(sessionID)
    run.isolation = isolation
    run.sandboxRuns += 1
    await this.publish(run)
    return this.snapshot(run)
  }

  status(sessionID: string) {
    const run = this.runFor(sessionID)
    return run ? this.snapshot(run) : this.snapshotOrInactive(sessionID)
  }

  private snapshotOrInactive(sessionID: string): HarnessStatus {
    return {
      sessionID,
      workspace: "",
      runId: "",
      goal: "",
      phase: "inactive",
      workers: [],
      activeCount: 0,
      queuedCount: 0,
      verificationState: "inactive",
      missingEvidence: [],
      repairCount: 0,
      maxSameFailureRepairs: 2,
      evidenceCount: 0,
      candidateCount: 0,
      evidenceRefs: [],
      candidateRefs: [],
      readyEligible: false,
      metrics: { observedActions: 0, workers: 0, activeWorkers: 0, repairs: 0, evidence: 0, sandboxRuns: 0 },
    }
  }

  private snapshot(run: RunRecord): HarnessStatus {
    const orchestration = this.orchestration.snapshot(run.sessionID)
    return {
      sessionID: run.sessionID,
      workspace: run.workspace,
      runId: run.runId,
      goal: run.goal,
      executionPlan: run.executionPlan,
      revisesPlan: run.revisesPlan,
      phase: run.interrupted ? "interrupted"
        : run.persistenceFailed ? "blocked"
        : run.graph && run.active.size > 0 && !run.integrationStarted ? "worker_running"
        : (orchestration?.phase ?? "inactive"),
      workers: [...run.workers.values()].map(({ unit: _unit, verification: _verification, ...worker }) => worker),
      activeCount: run.active.size,
      queuedCount: [...run.workers.values()].filter((worker) => worker.state === "queued").length,
      outcome: run.verification.outcome,
      verificationState: run.verification.state,
      contractStatus: run.contractAccepted ? "accepted" : "missing",
      configuredProfile: run.verification.configuredProfile ?? run.configuredProfile,
      effectiveProfile: run.verification.effectiveProfile ?? run.effectiveProfile,
      assuranceLevel: run.verification.assuranceLevel,
      failureKind: run.verification.failureKind,
      failedCriterion: run.verification.failedCriterion,
      missingEvidence: run.verification.missingEvidence ?? [],
      repairCount: run.verification.repairCount ?? 0,
      maxSameFailureRepairs: run.verification.maxSameFailureRepairs,
      evidenceCount: run.verification.evidenceRefs.length,
      candidateCount: run.verification.candidateRefs.length,
      evidenceRefs: artifactPaths(run.verification.evidenceRefs),
      candidateRefs: artifactPaths(run.verification.candidateRefs),
      readyEligible: run.verification.readyEligible === true,
      message: run.verification.message,
      isolation: run.isolation,
      metrics: {
        observedActions: run.observedActions.size,
        workers: run.workers.size,
        activeWorkers: run.active.size,
        repairs: run.verification.repairCount ?? 0,
        evidence: run.verification.evidenceRefs.length,
        sandboxRuns: run.sandboxRuns,
      },
    }
  }

  private async publish(run: RunRecord) {
    const previous = run.publication ?? Promise.resolve()
    const publication = previous.catch(() => undefined).then(async () => {
      if (!this.isCurrent(run)) return
      let status: HarnessStatus
      try {
        if (run.persistenceFailed) throw new Error("STATUS_PERSISTENCE_FAILED")
        await this.orchestration.flushPersistence(run.sessionID)
        status = this.persistence.redact(run.runId, this.snapshot(run))
        await this.repository.persist(status, run.interrupted)
        await this.statusCheckpoint?.(status)
      } catch (error) {
        const rawCode = (error as { code?: unknown } | undefined)?.code
        const code = typeof rawCode === "string" && /^[A-Z0-9_]{1,80}$/.test(rawCode) ? rawCode : "STATUS_PERSISTENCE_FAILED"
        // A failed durable sink is terminal for this run, not a code-repair instruction.
        run.persistenceFailed = true
        run.execution.abort()
        run.integrationComplete = false
        run.verification = {
          ...run.verification, state: "failure", outcome: "failure", failureKind: "harness_error",
          readyEligible: false, readyRef: null, scopeAttestation: null,
          message: "Host status persistence failed [" + code + "]. Resolve storage before starting a new run.",
        }
        run.rootExecutionFailure = run.verification
        run.executionFailures.set(run.sessionID, run.verification)
        this.orchestration.markOutcome(run.sessionID, "blocked")
        status = this.persistence.redact(run.runId, this.snapshot(run))
        // Best effort failure history; never retry a Ready publication or recurse into publish().
        await this.repository.persist(status, run.interrupted).catch(() => undefined)
        await this.statusCheckpoint?.(status).catch(() => undefined)
      }
      if (!this.isCurrent(run)) return
      // Do not publish an earlier Ready if the live run failed while the sink was pending.
      if (run.rootExecutionFailure || run.interrupted) status = this.persistence.redact(run.runId, this.snapshot(run))
      const waiters = [...run.settledWaiters]
      run.settledWaiters.clear()
      for (const resolve of waiters) resolve()
      for (const publisher of this.publishers) {
        try {
          void Promise.resolve(publisher(status)).catch(() => undefined)
        } catch {
          // Presentation delivery is observational; the durable checkpoint above is not.
        }
      }
    })
    run.publication = publication
    await publication
  }

  resetForTest() {
    for (const run of this.runs.values()) {
      run.interrupted = true
      run.execution.abort()
      void run.verifier?.close().catch(() => undefined)
    }
    this.repository.reset()
    this.candidates.reset()
    this.executor = undefined
    this.integrationExecutor = undefined
    this.publishers.clear()
    this.statusCheckpoint = undefined
  }
}

export const Coordinator = new CoordinatorRuntime()

export * from "./contracts"
export { RunRepository } from "./run-repository"
export { CandidateService } from "./candidate-service"

export type { GoalContractProposal, VerificationStatus }
