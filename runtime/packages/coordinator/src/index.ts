import * as Orchestration from "@base-harness/core/orchestration"
import {
  createFailureEnvelope,
  createGoalContract,
  createVerificationClient,
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
  active: Set<string>
  openedScopes: Set<string>
  observedActions: Set<string>
  pendingHostEvents: Array<{ type: string; data: unknown }>
  hostEvents: Promise<void>
  hostEventDepth: number
  maxParallel: number
  interrupted: boolean
  trigger: "auto" | "manual"
  contractAccepted: boolean
  graph?: Orchestration.WorkGraph
  integrationStarted: boolean
  integrationComplete: boolean
  settledWaiters: Set<() => void>
  rootVerification?: Promise<HarnessStatus>
  configuredProfile: VerificationProfile
  effectiveProfile: VerificationProfile
  isolation?: import("./contracts").IsolationStatus
  sandboxRuns: number
}

const record = (value: unknown): Record<string, unknown> | undefined =>
  value !== null && typeof value === "object" ? (value as Record<string, unknown>) : undefined

const stringValue = (value: unknown) => (typeof value === "string" ? value : undefined)

export class CoordinatorRuntime implements CoordinatorService {
  private readonly repository: RunRepository<RunRecord>
  private readonly candidates: CandidateService
  private readonly persistence: PersistenceGateway
  private executor?: WorkerExecutor
  private integrationExecutor?: IntegrationExecutor
  private readonly publishers = new Set<StatusPublisher>()

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

  registerWorkerExecutor(executor: WorkerExecutor) {
    this.executor = executor
  }

  registerIntegrationExecutor(executor: IntegrationExecutor) {
    this.integrationExecutor = executor
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

  private async disposeRun(run: RunRecord) {
    run.interrupted = true
    Orchestration.markInterrupted(run.sessionID)
    for (const resolve of run.settledWaiters) resolve()
    run.settledWaiters.clear()
    await run.verifier?.close().catch(() => undefined)
    this.persistence.closeRun(run.runId)
    this.repository.delete(run)
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
          goalContract: run.configuredProfile === "fast" ? createGoalContract(run.source, { risk: "low" }) : undefined,
          configuredProfile: run.configuredProfile,
          effectiveProfile: run.effectiveProfile,
        },
        { redactor: (value) => this.persistence.redact(run.runId, value) },
      )
      run.verification = run.verifier.snapshot()
      run.verifier.subscribe((status) => {
        run.verification = status
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
    this.candidates.activate()
    await this.repository.initialize()
    let existing = this.runs.get(input.sessionID)
    if (existing && existing.workspace !== input.workspace) {
      await this.disposeRun(existing)
      existing = undefined
    }
    if (existing) {
      if (input.context !== undefined) existing.context = input.context
      return this.snapshot(existing)
    }
    const runId = "run-" + input.sessionID
    this.persistence.openRun(runId)
    const source = goalSource(input.goal, "session-" + input.sessionID, "user_message")
    const profile = input.configuredProfile ?? "adaptive"
    const run: RunRecord = {
      sessionID: input.sessionID,
      runId,
      goal: input.goal,
      workspace: input.workspace,
      source,
      verification: inactiveVerification(runId, input.sessionID, input.maxSameFailureRepairs),
      workers: new Map(),
      draining: false,
      active: new Set(),
      openedScopes: new Set([input.sessionID]),
      observedActions: new Set(),
      pendingHostEvents: [],
      hostEvents: Promise.resolve(),
      hostEventDepth: 0,
      maxParallel: Math.max(1, Math.min(2, input.maxParallelWorkUnits ?? 2)),
      interrupted: false,
      trigger: input.trigger ?? "auto",
      contractAccepted: profile === "fast",
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

  async proposeContract(sessionID: string, proposal: GoalContractProposal) {
    const run = this.runFor(sessionID)
    if (!run) return this.snapshotOrInactive(sessionID)
    await this.ensureVerifier(run)
    if (!run.verifier) return this.snapshot(run)
    run.verification = await run.verifier.proposeContract(materializeProposal(run.source, proposal))
    run.contractAccepted = true
    const pending = run.pendingHostEvents.splice(0)
    for (const event of pending) await this.observeHostEvent(event.type, event.data)
    await this.publish(run)
    return this.snapshot(run)
  }

  async acceptWorkGraph(sessionID: string, graph: Orchestration.WorkGraph, context: unknown) {
    const run = this.runFor(sessionID)
    if (!run) throw new Error("Coordinator run is not open")
    if (graph.units.length > 64) throw new Error("WorkGraph exceeds the maximum of 64 WorkUnits")
    await Orchestration.acceptWorkGraph(run.sessionID, graph)
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
    if (run.draining || run.interrupted) return
    run.draining = true
    try {
      while (run.active.size < run.maxParallel) {
        const next = nextRunnable(run.workers)
        if (!next) break
        if (!this.executor || !run.context) {
          next.state = "failed"
          run.verification = {
            ...run.verification,
            state: "failure",
            outcome: "failure",
            failureKind: "harness_error",
            message: "Coordinator worker executor is unavailable.",
          }
          break
        }
        next.state = "running"
        run.active.add(next.workUnitId)
        void this.executeWorker(run, next)
      }
      this.finalizeScheduling(run)
      await this.publish(run)
    } finally {
      run.draining = false
    }
  }

  private async executeWorker(run: RunRecord, worker: WorkerRecord) {
    try {
      const result = await this.executor!({ rootSessionID: run.sessionID, unit: worker.unit, context: run.context })
      worker.scopeId = result.sessionID
      this.scopeRoots.set(result.sessionID, run.sessionID)
    } catch (error) {
      const state = worker.state as WorkerState
      if (state !== "repairing" && state !== "repair_exhausted") {
        worker.state = "failed"
        if (!nonRepairableFailure(run.verification.failureKind)) {
          run.verification = {
            ...run.verification,
            state: "failure",
            outcome: "failure",
            failureKind: "implementation_error",
            message: error instanceof Error ? error.message : String(error),
          }
        }
      }
    } finally {
      if ((worker.state as WorkerState) === "repairing") await this.executeRepair(run, worker)
      else {
        run.active.delete(worker.workUnitId)
        await this.publish(run)
        void this.drain(run)
      }
    }
  }

  private async executeRepair(run: RunRecord, worker: WorkerRecord): Promise<void> {
    if (!worker.scopeId || !this.executor || !run.context) {
      worker.state = "failed"
      run.active.delete(worker.workUnitId)
      void this.drain(run)
      return
    }
    Orchestration.reopenScope(worker.scopeId)
    await run.verifier?.reopenScope(worker.scopeId)
    worker.state = "running"
    const repairPrompt = workerRepairPrompt({
      fingerprint: worker.failureFingerprint,
      failedCriterion: run.verification.failedCriterion,
      missingEvidence: run.verification.missingEvidence,
    })
    try {
      await this.executor({
        rootSessionID: run.sessionID,
        unit: worker.unit,
        context: run.context,
        taskID: worker.scopeId,
        repairPrompt,
      })
    } catch (error) {
      const state = worker.state as WorkerState
      if (state !== "repairing" && state !== "repair_exhausted") {
        worker.state = "failed"
        if (!nonRepairableFailure(run.verification.failureKind)) {
          run.verification = {
            ...run.verification,
            state: "failure",
            outcome: "failure",
            failureKind: "implementation_error",
            message: error instanceof Error ? error.message : String(error),
          }
        }
      }
    }
    if ((worker.state as WorkerState) === "repairing") {
      await this.executeRepair(run, worker)
      return
    }
    run.active.delete(worker.workUnitId)
    await this.publish(run)
    void this.drain(run)
  }

  async finishWorker(sessionID: string, success: boolean) {
    const candidate = await Orchestration.finishChild(sessionID, success)
    const run = candidate ? this.runs.get(candidate.runId) : this.runFor(sessionID)
    if (!run) return
    const worker = candidate
      ? run.workers.get(candidate.workUnitId)
      : [...run.workers.values()].find((item) => item.scopeId === sessionID)
    if (!success || !candidate || !worker) {
      if (worker) worker.state = nonRepairableFailure(run.verification.failureKind) ? "failed" : "repairing"
      await this.publish(run)
      return
    }
    await run.hostEvents
    worker.scopeId = sessionID
    worker.state = "candidate_ready"
    this.scopeRoots.set(sessionID, run.sessionID)
    await this.ensureVerifier(run)
    if (!run.verifier) {
      worker.state = "failed"
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
      const candidateWorkspace = await Orchestration.materializeCandidate(candidate.candidateId)
      const attachedCandidate = { ...candidate, candidateWorkspace }
      await run.verifier.observe({
        scopeId: sessionID,
        claimIds: worker.unit.claimIds,
        tool: "candidate.patch",
        status: "completed",
        output: attachedCandidate,
      })
      await run.verifier.attachCandidate(attachedCandidate)
      Orchestration.markCandidateVerifying(candidate.candidateId)
      worker.state = "verifying"
      await this.publish(run)
      const verified = await run.verifier.verify("completion", sessionID, {
        claimIds: worker.unit.claimIds,
        criterionIds: worker.unit.criterionIds,
      })
      await Orchestration.releaseCandidateWorkspace(candidate.candidateId)
      run.verification = verified
      if (verified.outcome !== "scope_verified" || !verified.scopeAttestation) {
        worker.repairCount = verified.repairCount ?? worker.repairCount
        worker.failureFingerprint = verified.failureFingerprint
        worker.state =
          verified.outcome === "repair_exhausted"
            ? "repair_exhausted"
            : verified.outcome === "repair"
              ? "repairing"
              : "failed"
        await this.publish(run)
        return
      }
      worker.state = "committing"
      await this.publish(run)
      const attestation = verified.scopeAttestation
      await Orchestration.commitCandidate(candidate.candidateId, attestation)
      await run.verifier.commitCandidate(attestation, sessionID)
      worker.state = "completed"
      await this.publish(run)
    } catch (error) {
      if (candidate) await Orchestration.releaseCandidateWorkspace(candidate.candidateId).catch(() => undefined)
      worker.state = "failed"
      run.verification = {
        ...run.verification,
        state: "failure",
        outcome: "failure",
        failureKind: error instanceof Orchestration.OrchestrationError ? "workspace_conflict" : "verifier_error",
        message: error instanceof Error ? error.message : String(error),
      }
      await this.publish(run)
    }
  }

  private finalizeScheduling(run: RunRecord) {
    if (run.active.size > 0) return
    const workers = [...run.workers.values()]
    if (workers.length && workers.every((worker) => worker.state === "completed")) {
      void this.startIntegration(run)
      return
    }
    const runnable = workers.some(
      (worker) => worker.state === "queued" && this.dependenciesComplete(run, worker),
    )
    const terminalFailure = workers.some((worker) => worker.state === "failed" || worker.state === "repair_exhausted")
    if (!runnable && terminalFailure) {
      Orchestration.markOutcome(run.sessionID, "blocked")
      run.verification = {
        ...run.verification,
        state: "blocked",
        outcome: "blocked",
        message: run.verification.message ?? "No runnable WorkUnit remains for the unresolved required criteria.",
      }
    }
  }

  private async startIntegration(run: RunRecord) {
    if (run.integrationStarted || run.integrationComplete || run.interrupted) return
    run.integrationStarted = true
    await this.publish(run)
    if (!this.integrationExecutor || !run.context || !run.graph) {
      run.verification = {
        ...run.verification,
        state: "failure",
        outcome: "blocked",
        failureKind: "harness_error",
        message: "Coordinator root integration executor is unavailable.",
      }
      Orchestration.markOutcome(run.sessionID, "blocked")
      await this.publish(run)
      return
    }
    try {
      await this.integrationExecutor({
        rootSessionID: run.sessionID,
        context: run.context,
        integrationPaths: run.graph.integrationPaths,
        integrationRequests: run.graph.units.flatMap((unit) => unit.integrationRequests),
      })
      run.integrationComplete = true
      await this.publish(run)
      if (run.trigger === "auto") await this.verifyRoot(run.sessionID, "automatic")
    } catch (error) {
      run.verification = {
        ...run.verification,
        state: "failure",
        outcome: "blocked",
        failureKind: "harness_error",
        message: error instanceof Error ? error.message : String(error),
      }
      Orchestration.markOutcome(run.sessionID, "blocked")
      await this.publish(run)
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
    if (reason === "completion") await this.waitForSettled(run)
    if (this.pending(run)) return this.snapshot(run)
    await this.ensureVerifier(run)
    if (!run.verifier) return this.snapshot(run)
    await run.hostEvents
    if (run.rootVerification) return run.rootVerification
    const verification = (async () => {
      do {
        Orchestration.requestVerification(run.sessionID)
        const claimIds = run.verification.goalContract?.claims.map((claim) => claim.claimId) ?? []
        await run.verifier!.observe({
          scopeId: run.sessionID,
          claimIds,
          tool: "session.completion",
          status: "completed",
          metadata: { coordinator: true, isolation: run.isolation },
        })
        run.verification = await run.verifier!.verify(reason, run.sessionID)
        if (run.verification.outcome !== "repair") break
        if (!this.integrationExecutor || !run.context) {
          run.verification = {
            ...run.verification,
            state: "blocked",
            outcome: "blocked",
            failureKind: "harness_error",
            message: "Root repair requires the Coordinator integration executor.",
          }
          break
        }
        Orchestration.markOutcome(run.sessionID, "repair")
        run.integrationComplete = false
        await this.publish(run)
        await this.integrationExecutor({
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
        Orchestration.markOutcome(run.sessionID, run.verification.outcome === "repair" ? "blocked" : run.verification.outcome)
      } else if (run.verification.outcome === "repair_exhausted") {
        Orchestration.markOutcome(run.sessionID, "blocked")
      }
      await this.publish(run)
      return this.snapshot(run)
    })()
    run.rootVerification = verification
    try {
      return await verification
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
    if (!run || run.interrupted) return
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
        run.verification = await run.verifier.observe({
          scopeId: sessionID,
          claimIds,
          tool: stringValue(part.tool) ?? "tool",
          status,
          input: state?.input,
          output: state?.output,
          error: failure,
          metadata: { hostObserved: true, callId: stringValue(part.callID) },
        })
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
        run.verification = await run.verifier.observe({
          scopeId: sessionID,
          claimIds,
          tool: "model",
          status: "error",
          error: failure,
          metadata: { hostObserved: true },
        })
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
      run.verification = {
        ...run.verification,
        state: "failure",
        outcome: "failure",
        failureKind: "verifier_error",
        message: error instanceof Error ? error.message : String(error),
      }
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
    Orchestration.markInterrupted(run.sessionID)
    await run.verifier?.close().catch(() => undefined)
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
      readyEligible: false,
      metrics: { observedActions: 0, workers: 0, activeWorkers: 0, repairs: 0, evidence: 0, sandboxRuns: 0 },
    }
  }

  private snapshot(run: RunRecord): HarnessStatus {
    const orchestration = Orchestration.snapshot(run.sessionID)
    return {
      sessionID: run.sessionID,
      workspace: run.workspace,
      runId: run.runId,
      goal: run.goal,
      phase: run.interrupted ? "interrupted" : (orchestration?.phase ?? "inactive"),
      workers: [...run.workers.values()].map(({ unit: _unit, ...worker }) => worker),
      activeCount: run.active.size,
      queuedCount: [...run.workers.values()].filter((worker) => worker.state === "queued").length,
      outcome: run.verification.outcome,
      verificationState: run.verification.state,
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
    const status = this.persistence.redact(run.runId, this.snapshot(run))
    await this.repository.persist(status, run.interrupted)
    const waiters = [...run.settledWaiters]
    run.settledWaiters.clear()
    for (const resolve of waiters) resolve()
    for (const publisher of this.publishers) {
      try {
        void Promise.resolve(publisher(status)).catch(() => undefined)
      } catch {
        // Status delivery is observational and must not block the execution state machine.
      }
    }
  }

  resetForTest() {
    for (const run of this.runs.values()) void run.verifier?.close().catch(() => undefined)
    this.repository.reset()
    this.candidates.reset()
    this.executor = undefined
    this.integrationExecutor = undefined
    this.publishers.clear()
  }
}

export const Coordinator = new CoordinatorRuntime()

export * from "./contracts"
export { RunRepository } from "./run-repository"
export { CandidateService } from "./candidate-service"

export type { GoalContractProposal, VerificationStatus }
