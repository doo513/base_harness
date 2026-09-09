import {
  allowsOperation,
  applyControl,
  createKernelSessionState,
  decideContractPreflight,
  decidePlanning,
  operationForTool,
  parseInterpretationProposal,
  parseMetaReview,
  validateInterpretationBindings,
  validatePlanSpec,
  validatePlanCoverage,
  type HarnessControl,
  type ContractPreflightResult,
  type ContractRevalidationTrigger,
  type InterpretationProposal,
  type KernelSessionState,
  type MetaReviewPhase,
  type MetaReviewReport,
  type PlanSpec,
  type PlanningDecision,
  type PlanningSignals,
  type PreflightReason,
  type UncertaintyCandidate,
  type ToolOperation,
} from "@base-harness/kernel"
import { createHash, randomUUID } from "node:crypto"
import { readFile, realpath, stat } from "node:fs/promises"
import {
  ReviewedPlanStore, type ReviewedPlanRecord, type ReviewedPlanStoreOptions,
  type PlanExecutionPolicy, type PlanSelection, type PlanRevisionClaim,
} from "./reviewed-plan-store"
import path from "node:path"
import {
  SessionStateStore, sessionSelection, summarizeRun,
  type RunHistory, type SessionStateStoreOptions,
} from "./session-state-store"

export type { RunHistory, SessionStateStoreOptions } from "./session-state-store"
export interface KernelHostOptions extends ReviewedPlanStoreOptions {
  /** Production enables this explicitly; pure Kernel fixtures have no extra disk writes. */
  sessionState?: boolean | SessionStateStoreOptions
}

export interface MetaReviewRequest {
  phase: MetaReviewPhase
  sessionID: string
  runId: string
  artifact: unknown
  priorIssues: MetaReviewReport["issues"]
  attempt: number
  context?: unknown
}

export interface KernelStatus {
  domain: KernelSessionState["domain"]
  skills: KernelSessionState["skills"]
  execution?: KernelSessionState["execution"]
  planningPreference: KernelSessionState["planningPreference"]
  planningState: KernelSessionState["planningState"]
  planOnly: boolean
  history?: RunHistory
  planRecovery?: { code: "PLAN_REVISION_PENDING"; action: "planning.discard"; planId: string; revision: number }
  planningDecision?: PlanningDecision
  activePlanId?: string
  activePlanRevision?: number
  goalContract?: {
    revision: number
    hash?: string
    claims: Array<{
      id: string
      statement: string
      required: boolean
      criterionIds: string[]
    }>
    criteria: Array<{
      id: string
      statement: string
      required: boolean
      risk?: string
      claimIds: string[]
    }>
  }
  plan?: {
    id: string
    revision: number
    assumptions: string[]
    steps: PlanSpec["steps"]
  }
  preflight?: ContractPreflightStatus
  metaReview?: {
    phase: MetaReviewPhase
    outcome: MetaReviewReport["outcome"]
    issueCount: number
    blockingIssueCount: number
    issues: MetaReviewReport["issues"]
  }
}

export interface ContractPreflightStatus extends ContractPreflightResult {
  candidateCount: number
  questionCount: number
  assumptionCount: number
  reviewerCallCount: number
  requiredDecisions: Array<{
    id: string
    statement: string
    suggestedResolution?: string
    impact: UncertaintyCandidate["impact"]
    affectedClaimIds: string[]
    affectedCriterionIds: string[]
  }>
  assumptions: string[]
  revalidationTrigger?: ContractRevalidationTrigger
}

interface SessionRecord {
  state: KernelSessionState
  runId?: string
  workspace?: string
  goal?: string
  context?: unknown
  contract?: unknown
  contractHash?: string
  contractRevision: number
  graph?: unknown
  graphContext?: unknown
  plan?: PlanSpec
  decision?: PlanningDecision
  review?: MetaReviewReport
  preflight?: ContractPreflightStatus
  revisionOnly?: boolean
  explicitSelection?: boolean
  executionStarting?: boolean
  restored?: boolean
  savedPlan?: ReviewedPlanRecord
  revisionClaim?: PlanRevisionClaim
  pendingRevision?: ReviewedPlanRecord
  hydration?: Promise<void>
  runPolicy?: PlanExecutionPolicy
  history?: RunHistory
  historyWorkspace?: string
  historyLoaded?: boolean
}

interface RuntimeCoordinator {
  openRun(input: any): Promise<any>
  proposeContract(sessionID: string, proposal: any): Promise<any>
  acceptWorkGraph(sessionID: string, graph: any, context?: unknown): Promise<any>
  status(sessionID: string): any
  cancel?(sessionID: string): Promise<any>
  beginPlanExecution?(sessionID: string, input: {
    planningRunId: string
    planId: string
    planRevision: number
    goalContractHash: string
    context?: unknown
  }): Promise<any>
  beginRestoredPlanExecution?(sessionID: string, input: any): Promise<any>
  reportPlanExecutionFailure?(sessionID: string, error: unknown): Promise<unknown>
  beginDirect?(sessionID: string): void
  beginPlanning?(sessionID: string): void
  isInternalContinuation?(sessionID: string): boolean
  reportMetaReviewFailure?(
    sessionID: string, error: unknown, phase: string, source?: "harness" | "model" | "tool",
  ): Promise<unknown>
}

const canonicalWorkspace = (value: string) => process.platform === "win32" ? path.resolve(value).toLowerCase() : path.resolve(value)

export class KernelHost {
  private readonly sessions = new Map<string, SessionRecord>()
  private reviewer?: (request: MetaReviewRequest) => Promise<unknown>
  private readonly listeners = new Set<(status: any) => void>()

  private readonly plans: ReviewedPlanStore
  private readonly sessionStore?: SessionStateStore
  private readonly controls = new Map<string, Promise<any>>()
  private readonly executeControls = new Set<string>()

  constructor(private readonly runtime: RuntimeCoordinator, options: KernelHostOptions = {}) {
    this.plans = new ReviewedPlanStore(options)
    if (options.sessionState) this.sessionStore = new SessionStateStore({
      redact: options.redact,
      ...(typeof options.sessionState === "object" ? options.sessionState : {}),
    })
  }

  /** Awaited Host checkpoint, not a presentation subscriber and not an actor-facing API. */
  async checkpointStatus(status: any) {
    if (!this.sessionStore || !status.runId || !status.workspace) return
    const record = this.session(status.sessionID)
    const history = summarizeRun(this.mergeStatus(status.sessionID, status))
    await this.sessionStore.save({
      sessionID: status.sessionID, workspace: status.workspace,
      selection: sessionSelection(record.state), lastRun: history,
    })
    record.history = history
    record.historyWorkspace = status.workspace
    record.historyLoaded = true
  }

  private async persistSelection(sessionID: string, state: KernelSessionState, workspace?: string) {
    if (!this.sessionStore) return
    const record = this.session(sessionID)
    const directory = workspace ?? record.workspace ?? record.historyWorkspace
    if (!directory) throw kernelError("SESSION_WORKSPACE_REQUIRED")
    await this.sessionStore.save({
      sessionID, workspace: directory, selection: sessionSelection(state), lastRun: record.history,
    })
    record.historyWorkspace = directory
    record.historyLoaded = true
  }

  async resolvePlan(planId: string) {
    const saved = await this.plans.load({ planId })
    return { sessionID: saved.sessionID, workspace: saved.workspace,
      planId: saved.plan.planId, revision: saved.plan.revision }
  }

  async preparePlanExecution(sessionID: string, workspace: string, planId?: string) {
    const record = this.session(sessionID)
    if (record.executionStarting) throw kernelError("RUN_ACTIVE")
    if (record.plan && planId && record.plan.planId !== planId) throw kernelError("PLAN_ID_MISMATCH")
    this.assertPlanningRunAvailable(sessionID)
    const saved = await this.plans.load({ sessionID, planId: planId ?? record.plan?.planId })
    if (await realpath(workspace) !== await realpath(saved.workspace)) throw kernelError("PLAN_WORKSPACE_MISMATCH")
    this.validateReviewedPlan(saved)
    await assertPlanFresh(saved.plan, saved.workspace)
    if (!saved.selection) throw kernelError("PLAN_SELECTION_UNAVAILABLE")
    if (record.runId) {
      if (record.state.planningState !== "plan_ready" || digest(record.plan) !== digest(saved.plan)
          || record.state.domain !== saved.state.domain || digest(record.state.skills) !== digest(saved.state.skills)
          || digest(record.state.execution ?? null) !== digest(saved.state.execution ?? null)) throw kernelError("PLAN_STALE")
    } else {
      const current = this.runtime.status(sessionID)
      if (current.runId && current.phase !== "inactive") throw kernelError("RUN_ACTIVE")
      this.restoreReviewedPlan(record, saved)
    }
    return { selection: saved.selection, policy: saved.policy }
  }

  private validateReviewedPlan(saved: ReviewedPlanRecord) {
    validatePlanSpec(saved.plan)
    assertContractProposal(saved.contract)
    validatePlanCoverage(saved.plan, requiredIDs(saved.contract, "claims", "claimId"),
      requiredIDs(saved.contract, "criteria", "criterionId"))
    if (digest(saved.contract) !== saved.plan.goalContractHash
        || saved.state.domain !== saved.plan.domain || digest(saved.state.skills) !== digest(saved.plan.skills)
        || saved.state.activePlanId !== saved.plan.planId || saved.state.activePlanRevision !== saved.plan.revision) {
      throw kernelError("PLAN_INTEGRITY_INVALID")
    }
    reviewedExecutionGraph(saved.plan, saved.plan)
  }

  private restoreReviewedPlan(record: SessionRecord, saved: ReviewedPlanRecord) {
    Object.assign(record, {
      state: structuredClone(saved.state), runId: saved.plan.runId, workspace: saved.workspace, goal: saved.goal,
      contract: structuredClone(saved.contract), contractHash: saved.plan.goalContractHash,
      contractRevision: saved.plan.goalContractRevision, plan: structuredClone(saved.plan),
      graph: structuredClone(saved.plan.workGraph), decision: "planned", review: structuredClone(saved.review),
      preflight: saved.preflight, runPolicy: saved.policy, savedPlan: saved, restored: true,
      // A recovered session already has an authoritative domain/skill selection.
      explicitSelection: true,
      revisionClaim: undefined, pendingRevision: undefined, revisionOnly: false,
    })
  }

  private clearReviewedPlan(record: SessionRecord) {
    Object.assign(record, {
      state: applyControl(record.state, { type: "planning.discard" }),
      runId: undefined, workspace: undefined, goal: undefined, context: undefined,
      contract: undefined, contractHash: undefined, contractRevision: 0,
      graph: undefined, graphContext: undefined, plan: undefined, decision: undefined,
      review: undefined, preflight: undefined, savedPlan: undefined, revisionClaim: undefined,
      pendingRevision: undefined, revisionOnly: false, restored: false, runPolicy: undefined,
    })
  }

  /** Hydrate presentation and planning intent only, never a verifier, worker or execution capability. */
  async readStatus(sessionID: string, workspace?: string) {
    const record = this.session(sessionID)
    if ((!record.runId || record.pendingRevision) && !record.executionStarting) {
      record.hydration ??= (async () => {
        const current = this.runtime.status(sessionID)
        if (current.runId && current.phase !== "inactive") return
        if (this.sessionStore && !record.historyLoaded) {
          const saved = await this.sessionStore.load(sessionID, workspace)
          if (saved) {
            record.state = { ...createKernelSessionState(), ...saved.selection }
            record.history = saved.lastRun
            record.historyWorkspace = saved.workspace
            record.explicitSelection = true
          }
          record.historyLoaded = true
        }
        const pending = await this.plans.findPending(sessionID)
        if (!pending) {
          if (record.pendingRevision) this.clearReviewedPlan(record)
          return
        }
        this.validateReviewedPlan(pending.record)
        if ((!record.runId || record.pendingRevision) && !record.executionStarting) {
          this.restoreReviewedPlan(record, pending.record)
          if (pending.state === "revision_pending") {
            record.pendingRevision = pending.record
            record.savedPlan = undefined
            record.revisionOnly = true
            record.state = { ...record.state, planningState: "awaiting_input" }
          }
        }
      })()
      try {
        await record.hydration
      } finally {
        record.hydration = undefined
      }
    }
    if (workspace && record.restored
        && await realpath(workspace) !== await realpath(record.workspace!)) {
      throw kernelError("PLAN_WORKSPACE_MISMATCH")
    }
    if (workspace && record.historyWorkspace
        && canonicalWorkspace(await realpath(workspace)) !== canonicalWorkspace(await realpath(record.historyWorkspace))) {
      throw kernelError("SESSION_WORKSPACE_MISMATCH")
    }
    // A GET must not publish an old plan_ready or history event into a new execution stream.
    return this.status(sessionID)
  }

  subscribe(listener: (status: any) => void) {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private emitStatus(sessionID: string, status: any) {
    const result = this.mergeStatus(sessionID, status)
    for (const listener of this.listeners) {
      try { listener(result) } catch { /* Presentation cannot change execution policy. */ }
    }
    return result
  }

  registerMetaReviewer(reviewer: (request: MetaReviewRequest) => Promise<unknown>) {
    this.reviewer = reviewer
  }

  private session(sessionID: string): SessionRecord {
    let record = this.sessions.get(sessionID)
    if (!record) {
      record = { state: createKernelSessionState(), contractRevision: 0 }
      this.sessions.set(sessionID, record)
    }
    return record
  }

  private assertPlanningRunAvailable(sessionID: string, status = this.runtime.status(sessionID)) {
    if (["blocked", "interrupted", "failure"].includes(status?.phase) || status?.outcome === "failure") {
      throw kernelError("PLAN_RUN_BLOCKED")
    }
  }

  async openRun(input: any) {
    if (!this.runtime.isInternalContinuation?.(input.sessionID)) await this.controls.get(input.sessionID)
    await this.readStatus(input.sessionID, input.workspace)
    const record = this.session(input.sessionID)
    if (record.pendingRevision) throw kernelError("PLAN_REVISION_PENDING")
    if (this.runtime.isInternalContinuation?.(input.sessionID)) {
      const current = this.runtime.status(input.sessionID)
      if (record.runId !== current.runId || record.workspace !== input.workspace
          || record.state.planningState !== "executing" || !record.contractHash) {
        throw kernelError("ROOT_CONTINUATION_MISMATCH")
      }
      return this.emitStatus(input.sessionID, current)
    }
    if (record.executionStarting) throw kernelError("RUN_ACTIVE")
    record.executionStarting = true
    try {
      if (["ready", "blocked", "interrupted"].includes(this.runtime.status(input.sessionID)?.phase)
          && !record.revisionClaim && record.state.planningState !== "plan_ready") {
        const preference = record.state.planningPreference
        this.clearReviewedPlan(record)
        record.state.planningPreference = preference
      }
      if (!record.runId && !record.explicitSelection && input.defaultDomain) {
        record.state = applyControl(record.state, {
          type: "domain.set",
          domain: input.defaultDomain,
        })
      }
      const revisesPlan = record.state.planningState === "plan_ready" && record.plan
        ? { planningRunId: record.runId!, planId: record.plan.planId,
            planRevision: record.plan.revision, goalContractHash: record.plan.goalContractHash }
        : undefined
      if (record.state.planningState === "plan_ready") {
        if (record.savedPlan) record.revisionClaim = await this.plans.consume(record.savedPlan, "revise")
        record.savedPlan = undefined
        record.revisionOnly = true
        record.state = { ...record.state, planningState: "plan_building" }
      } else {
        record.state = { ...record.state, planningState: "contract_building" }
        record.review = undefined
        record.preflight = undefined
      }
      record.runPolicy = {
        configuredProfile: input.configuredProfile ?? "adaptive",
        effectiveProfile: input.effectiveProfile ?? input.configuredProfile ?? "adaptive",
        trigger: input.trigger ?? "auto",
        maxSameFailureRepairs: input.maxSameFailureRepairs ?? 2,
        maxParallelWorkUnits: Math.max(1, Math.min(2, input.maxParallelWorkUnits ?? 2)),
      }
      record.restored = false
      record.workspace = input.workspace
      record.goal = input.goal
      record.context = input.context
      const result = await this.runtime.openRun({ ...input, revisesPlan })
      record.runId = result.runId
      return this.emitStatus(input.sessionID, result)
    } catch (error) {
      if (record.revisionClaim) {
        record.pendingRevision = record.revisionClaim.record
        record.revisionOnly = true
        record.state = { ...record.state, planningState: "awaiting_input" }
      }
      throw error
    } finally {
      record.executionStarting = false
    }
  }

  async proposeContract(sessionID: string, proposal: unknown, context?: unknown) {
    const record = this.session(sessionID)
    if (context) record.context = context
    record.review = undefined
    record.state = { ...record.state, planningState: "contract_preflight" }
    let normalized = normalizeContractProposal(proposal)
    assertContractProposal(normalized.contract)
    validateInterpretationBindings(
      normalized.interpretation,
      allIDs(normalized.contract, "claims", "claimId"),
      allIDs(normalized.contract, "criteria", "criterionId"),
    )
    let result = decideContractPreflight(
      normalized.interpretation,
      contractPreflightSignals(
        normalized.contract,
        verificationProfile(this.runtime.status(sessionID)),
      ),
    )
    record.preflight = preflightStatus(result, normalized.interpretation)
    if (result.decision === "needs_input") {
      record.state = { ...record.state, planningState: "awaiting_input" }
      return this.emitStatus(sessionID, this.runtime.status(sessionID))
    }
    if (result.decision === "meta_review_required") {
      record.state = { ...record.state, planningState: "contract_reviewing" }
      const reviewed = await this.review(sessionID, "goal_contract", proposal)
      if (reviewed.report.outcome !== "pass") {
        record.state = { ...record.state, planningState: "awaiting_input" }
        return this.emitStatus(sessionID, this.runtime.status(sessionID))
      }
      normalized = normalizeContractProposal(reviewed.artifact)
      assertContractProposal(normalized.contract)
      validateInterpretationBindings(
        normalized.interpretation,
        allIDs(normalized.contract, "claims", "claimId"),
        allIDs(normalized.contract, "criteria", "criterionId"),
      )
      result = decideContractPreflight(
        normalized.interpretation,
        contractPreflightSignals(
          normalized.contract,
          verificationProfile(this.runtime.status(sessionID)),
        ),
      )
      record.preflight = preflightStatus(
        result.decision === "meta_review_required"
          ? { ...result, decision: "accept", mutatingActionAllowed: true }
          : result,
        normalized.interpretation,
        record.preflight?.reviewerCallCount ?? 0,
        reviewed.report.issues
          .filter((issue) => issue.severity === "warning")
          .map((issue) => issue.statement),
      )
      if (result.decision === "needs_input") {
        record.state = { ...record.state, planningState: "awaiting_input" }
        return this.emitStatus(sessionID, this.runtime.status(sessionID))
      }
    }
    // A preflight proposal cannot authorize mutation before runtime acceptance.
    if (record.preflight) record.preflight.mutatingActionAllowed = false
    const runtimeResult = await this.runtime.proposeContract(sessionID, normalized.contract)
    if (runtimeResult.contractStatus !== "accepted") {
      record.state = { ...record.state, planningState: "contract_building" }
      return this.emitStatus(sessionID, runtimeResult)
    }
    this.assertPlanningRunAvailable(sessionID, runtimeResult)
    if (record.preflight) record.preflight.mutatingActionAllowed = true
    record.contract = normalized.contract
    record.contractRevision += 1
    record.contractHash = digest(normalized.contract)
    record.decision = record.revisionOnly
      ? "planned"
      : decidePlanning(record.state, planningSignals(normalized.contract, undefined))
    record.state = {
      ...record.state,
      planningState: record.decision === "direct" ? "executing" : "planning_decision",
    }
    if (record.decision === "direct") this.runtime.beginDirect?.(sessionID)
    else this.runtime.beginPlanning?.(sessionID)
    return this.emitStatus(sessionID, runtimeResult)
  }

  async acceptWorkGraph(sessionID: string, graph: any, context?: unknown) {
    const record = this.session(sessionID)
    if (context) record.context = context
    record.graphContext = context
    if (!record.contract || !record.contractHash || !record.workspace || !record.runId) {
      throw kernelError("CONTRACT_REQUIRED")
    }
    this.assertPlanningRunAvailable(sessionID)
    const executionGraph = structuredClone(record.state.skills.includes("hackathon")
      ? prioritizeDemoGraph(graph)
      : graph)
    const decision = record.revisionOnly
      ? "planned"
      : decidePlanning(record.state, planningSignals(record.contract, executionGraph))
    record.decision = decision
    if (decision === "direct" && record.state.planningPreference !== "plan_once") {
      record.state = { ...record.state, planningState: "executing" }
      this.runtime.beginDirect?.(sessionID)
      return this.emitStatus(sessionID, this.runtime.status(sessionID))
    }

    this.runtime.beginPlanning?.(sessionID)
    record.state = { ...record.state, planningState: "plan_building" }
    const plan = await this.buildPlan(record, executionGraph)
    record.state = { ...record.state, planningState: "plan_reviewing" }
    const reviewed = await this.review(sessionID, "plan", plan)
    if (reviewed.report.outcome !== "pass") {
      record.state = { ...record.state, planningState: "awaiting_input" }
      return this.emitStatus(sessionID, this.runtime.status(sessionID))
    }
    this.assertPlanningRunAvailable(sessionID)
    const canonical = structuredClone(reviewed.artifact) as PlanSpec
    canonical.assumptions = [
      ...new Set([
        ...canonical.assumptions,
        ...reviewed.report.issues
          .filter((issue) => issue.severity === "warning")
          .map((issue) => issue.statement),
      ]),
    ]
    validatePlanSpec(canonical)
    validatePlanCoverage(canonical, requiredIDs(record.contract, "claims", "claimId"), requiredIDs(record.contract, "criteria", "criterionId"))
    const reviewedGraph = reviewedExecutionGraph(canonical, plan)
    const actualBasis = await hashBasis(record.workspace, reviewedGraph.units.flatMap((unit: any) => unit.readSet ?? []))
    if (digest(actualBasis) !== digest(canonical.basis)) throw kernelError("PLAN_BASIS_MISMATCH")
    this.assertPlanningRunAvailable(sessionID)
    const planOnly = record.state.planningPreference === "plan_once" || record.revisionOnly === true
    const planState: KernelSessionState = {
      ...record.state,
      planningPreference: "auto",
      planningState: planOnly ? "plan_ready" : "executing",
      activePlanId: canonical.planId,
      activePlanRevision: canonical.revision,
    }
    const saved: ReviewedPlanRecord = {
      schemaVersion: "reviewed-plan-v1", sessionID, workspace: record.workspace, goal: record.goal ?? "",
      plan: canonical, contract: record.contract, state: { ...planState, planningState: "plan_ready" },
      review: reviewed.report, preflight: record.preflight, policy: record.runPolicy!,
      selection: selectionForPlan(context),
    }
    try {
      record.savedPlan = await this.plans.save(saved, record.revisionClaim)
    } catch (error) {
      record.pendingRevision = record.revisionClaim?.record
      record.state = { ...record.state, planningState: "awaiting_input" }
      await this.runtime.reportMetaReviewFailure?.(sessionID, error, "plan_persistence", "harness")
      this.emitStatus(sessionID, this.runtime.status(sessionID))
      throw error
    }
    record.revisionClaim = undefined
    record.pendingRevision = undefined
    record.revisionOnly = false
    record.graph = reviewedGraph
    record.plan = canonical
    record.graphContext = withPlanContext(context, canonical)
    if (!planOnly) {
      this.assertPlanningRunAvailable(sessionID)
      await this.plans.consume(record.savedPlan, "execute")
      record.savedPlan = undefined
    }
    record.state = planState
    if (planOnly) {
      await this.checkpointStatus(this.runtime.status(sessionID))
      return this.emitStatus(sessionID, this.runtime.status(sessionID))
    }
    return this.emitStatus(
      sessionID,
      await this.runtime.acceptWorkGraph(sessionID, reviewedGraph, record.graphContext),
    )
  }

  async control(sessionID: string, control: HarnessControl, context?: unknown, workspace?: string) {
    const execute = control.type === "planning.execute"
    // Reserve before queueing or awaiting: duplicate execution must not wait for
    // a handoff that may itself be waiting for user input or a remote runtime.
    if (execute && this.executeControls.has(sessionID)) throw kernelError("RUN_ACTIVE")
    if (execute) this.executeControls.add(sessionID)
    const prior = this.controls.get(sessionID) ?? Promise.resolve()
    const operation = prior.catch(() => undefined).then(() => this.applySessionControl(sessionID, control, context, workspace))
    this.controls.set(sessionID, operation)
    try { return await operation } finally {
      if (this.controls.get(sessionID) === operation) this.controls.delete(sessionID)
      if (execute) this.executeControls.delete(sessionID)
    }
  }

  private async applySessionControl(sessionID: string, control: HarnessControl, context?: unknown, workspace?: string) {
    await this.readStatus(sessionID, workspace)
    const record = this.session(sessionID)
    const selectionWorkspace = workspace ?? record.workspace ?? record.historyWorkspace
    if (record.executionStarting) throw kernelError("RUN_ACTIVE")
    if (record.pendingRevision) {
      if (control.type !== "planning.discard") throw kernelError("PLAN_REVISION_PENDING")
      record.executionStarting = true
      try {
        await this.plans.discardRevision(record.pendingRevision)
        if (this.runtime.status(sessionID).runId === record.runId) await this.runtime.cancel?.(sessionID)
        this.clearReviewedPlan(record)
        await this.persistSelection(sessionID, record.state, selectionWorkspace)
        return this.emitStatus(sessionID, this.runtime.status(sessionID))
      } finally {
        record.executionStarting = false
      }
    }
    if (control.type === "planning.execute") this.assertPlanningRunAvailable(sessionID)
    if (!record.restored && record.state.planningState !== "plan_ready"
        && ["ready", "blocked", "interrupted"].includes(this.runtime.status(sessionID)?.phase)) {
      record.state = { ...record.state, planningState: "idle" }
    }
    const active =
      record.state.planningState !== "idle" &&
      record.state.planningState !== "plan_ready" &&
      record.state.planningState !== "awaiting_input"
    if (active) throw kernelError("RUN_ACTIVE")
    if (control.type === "planning.execute") {
      if (record.state.planningState !== "plan_ready" || !record.plan || !record.graph) {
        throw kernelError("PLAN_NOT_READY")
      }
      if (control.planId && control.planId !== record.plan.planId) throw kernelError("PLAN_ID_MISMATCH")
      if (record.restored ? !this.runtime.beginRestoredPlanExecution : !this.runtime.beginPlanExecution) {
        throw kernelError("PLAN_EXECUTION_UNAVAILABLE")
      }
      record.executionStarting = true
      let handoffStarted = false
      try {
        try {
          await assertPlanFresh(record.plan, record.workspace!)
        } catch (error) {
          if ((error as { code?: string })?.code === "PLAN_STALE") {
            this.markRevalidation(record, "plan_basis_changed")
            this.emitStatus(sessionID, this.runtime.status(sessionID))
          }
          throw error
        }
        if (
          record.plan.domain !== record.state.domain ||
          digest(record.plan.skills) !== digest(record.state.skills) ||
          record.plan.goalContractHash !== record.contractHash ||
          record.plan.goalContractRevision !== record.contractRevision ||
          record.plan.planId !== record.state.activePlanId ||
          record.plan.revision !== record.state.activePlanRevision
        ) {
          this.markRevalidation(record, "plan_basis_changed")
          this.emitStatus(sessionID, this.runtime.status(sessionID))
          throw kernelError("PLAN_STALE")
        }
        if (context) record.graphContext = withPlanContext(context, record.plan)
        if (record.savedPlan) await this.plans.consume(record.savedPlan, "execute")
        record.savedPlan = undefined
        const planningRunId = record.runId!
        handoffStarted = true
        // Keep mutation and completion disabled while the new verifier accepts the same contract.
        record.state = { ...record.state, planningState: "plan_building" }
        this.emitStatus(sessionID, this.runtime.status(sessionID))
        const input = {
          planningRunId, planId: record.plan.planId, planRevision: record.plan.revision,
          goalContractHash: record.plan.goalContractHash, context: record.graphContext,
        }
        const execution = record.restored
          ? await this.runtime.beginRestoredPlanExecution!(sessionID, {
              ...input, ...record.runPolicy, workspace: record.workspace, goal: record.goal, contract: record.contract,
            })
          : await this.runtime.beginPlanExecution!(sessionID, input)
        record.restored = false
        record.runId = execution.runId
        if (!record.runId || record.runId === planningRunId) throw kernelError("PLAN_EXECUTION_RUN_INVALID")
        if (execution.contractStatus !== "accepted" || ["blocked", "failure"].includes(execution.phase)
            || ["repair", "blocked", "failure", "needs_input", "repair_exhausted"].includes(execution.outcome)) {
          record.state = { ...record.state, planningState: "awaiting_input" }
          return this.emitStatus(sessionID, execution)
        }
        record.state = { ...record.state, planningState: "executing" }
        await this.runtime.acceptWorkGraph(sessionID, record.graph, record.graphContext)
        return this.emitStatus(sessionID, this.runtime.status(sessionID))
      } catch (error) {
        if (handoffStarted) {
          // A Host dispatch failure is not an unresolved user decision.
          record.state = { ...record.state, planningState: "idle" }
          await this.runtime.reportPlanExecutionFailure?.(sessionID, error)
          this.emitStatus(sessionID, this.runtime.status(sessionID))
        }
        throw error
      } finally {
        record.executionStarting = false
      }
    }
    if (record.savedPlan && ["planning.discard", "domain.set", "skill.set", "execution.select"].includes(control.type)) {
      await this.plans.consume(record.savedPlan, "discard")
      record.savedPlan = undefined
    }
    if (control.type === "planning.discard") {
      if (record.state.planningState !== "plan_ready" && record.state.planningState !== "awaiting_input") {
        throw kernelError("PLAN_NOT_DISCARDABLE")
      }
      if (this.runtime.status(sessionID).runId === record.runId) await this.runtime.cancel?.(sessionID)
      this.clearReviewedPlan(record)
    }
    const selected = applyControl(record.state, control)
    await this.persistSelection(sessionID, selected, selectionWorkspace)
    record.state = selected
    if (control.type === "domain.set" || control.type === "skill.set") record.explicitSelection = true
    return this.emitStatus(sessionID, this.runtime.status(sessionID))
  }

  assertToolAllowed(
    sessionID: string, toolID: string, subagentType?: string,
    hostOperation?: ToolOperation,
  ) {
    const record = this.session(sessionID)
    const operation = hostOperation ?? operationForTool(toolID)
    if (record.state.domain === "general" && operation === "unknown") {
      throw kernelError("DOMAIN_PERMISSION_UNKNOWN")
    }
    if (!allowsOperation(record.state, operation, subagentType)) {
      throw kernelError(
        record.state.domain === "general" ? "DOMAIN_PERMISSION_DENIED" : "PLAN_ONLY_MUTATION_DENIED",
      )
    }
  }

  /** Kernel admission only; the Coordinator still enforces run, worker and verifier gates. */
  canVerifyRoot(sessionID: string) {
    return this.session(sessionID).state.planningState === "executing"
  }

  status(sessionID: string) {
    return this.mergeStatus(sessionID, this.runtime.status(sessionID))
  }

  revalidateContract(
    sessionID: string,
    trigger: ContractRevalidationTrigger,
    affectedClaimIds: string[] = [],
    affectedCriterionIds: string[] = [],
  ) {
    const record = this.session(sessionID)
    this.markRevalidation(record, trigger, affectedClaimIds, affectedCriterionIds)
    return this.status(sessionID)
  }

  private mergeStatus(sessionID: string, status: any) {
    const record = this.session(sessionID)
    const kernel: KernelStatus = {
      domain: record.state.domain,
      skills: record.state.skills,
      execution: record.state.execution,
      planningPreference: record.state.planningPreference,
      // Terminal runs have no planning work in flight. Do not mutate admission state.
      planningState: record.state.planningState === "executing"
        && ["ready", "blocked", "failure", "interrupted"].includes(status.phase)
        ? "idle" : record.state.planningState,
      planOnly: record.revisionOnly === true || record.state.planningPreference === "plan_once"
        || record.state.planningState === "plan_ready",
      planRecovery: record.pendingRevision ? {
        code: "PLAN_REVISION_PENDING", action: "planning.discard",
        planId: record.pendingRevision.plan.planId, revision: record.pendingRevision.plan.revision,
      } : undefined,
      planningDecision: record.decision,
      activePlanId: record.state.activePlanId,
      activePlanRevision: record.state.activePlanRevision,
      goalContract: contractStatus(record),
      plan: record.plan
        ? {
            id: record.plan.planId,
            revision: record.plan.revision,
            assumptions: record.plan.assumptions,
            steps: record.plan.steps,
          }
        : undefined,
      preflight: record.preflight,
      metaReview: record.review
        ? {
            phase: record.review.phase,
            outcome: record.review.outcome,
            issueCount: record.review.issues.length,
            blockingIssueCount: record.review.issues.filter((issue) => issue.severity === "blocking").length,
            issues: record.review.issues,
          }
        : undefined,
    }
    const preview = record.restored && status.phase === "inactive" && record.state.planningState === "plan_ready"
      ? {
          runId: record.runId, workspace: record.workspace, goal: record.goal, phase: "plan_ready",
          configuredProfile: record.runPolicy?.configuredProfile, effectiveProfile: record.runPolicy?.effectiveProfile,
          maxSameFailureRepairs: record.runPolicy?.maxSameFailureRepairs,
          verificationState: "inactive", readyEligible: false,
        }
      : {}
    const recovery = record.pendingRevision ? {
      runId: record.runId, workspace: record.workspace, goal: record.goal,
      phase: "blocked", outcome: "needs_input", verificationState: "inactive", readyEligible: false,
      message: "A plan revision is pending in another Host or was interrupted. Use /plan discard before starting a new plan.",
    } : {}
    const history = status.phase === "inactive" && !record.runId && !record.restored
      && !record.executionStarting ? record.history : undefined
    // History stays nested: active run ID, evidence counts and Ready eligibility remain inactive.
    return { ...status, ...preview, ...recovery, ...kernel, history }
  }

  private async review(sessionID: string, phase: MetaReviewPhase, original: unknown) {
    if (!this.reviewer) {
      const error = kernelError("META_REVIEWER_UNAVAILABLE")
      await this.runtime.reportMetaReviewFailure?.(sessionID, error, phase, "harness")
      throw error
    }
    let artifact = original
    let priorIssues: MetaReviewReport["issues"] = []
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      let raw: unknown
      try {
        if (phase === "goal_contract" && this.session(sessionID).preflight) {
          this.session(sessionID).preflight!.reviewerCallCount += 1
        }
        raw = await this.reviewer({
          phase,
          sessionID,
          runId: this.session(sessionID).runId ?? "",
          artifact,
          priorIssues,
          attempt,
          context: this.session(sessionID).context,
        })
      } catch (error) {
        // Dispatch, transport and Host failures are not malformed model responses.
        await this.runtime.reportMetaReviewFailure?.(sessionID, error, phase, "harness")
        throw error
      }
      let report: MetaReviewReport
      try {
        report = parseMetaOutput(raw, phase)
      } catch (error) {
        if (attempt === 2) {
          const failure = kernelError("META_REVIEW_MODEL_PROTOCOL", error)
          await this.runtime.reportMetaReviewFailure?.(sessionID, {
            name: "InvalidProviderOutput", code: "META_REVIEW_MODEL_PROTOCOL", message: failure.message,
          }, phase, "model")
          throw failure
        }
        continue
      }
      this.session(sessionID).review = report
      if (report.outcome === "pass" || report.outcome === "needs_input") return { report, artifact }
      priorIssues = report.issues
      if (report.revisedArtifact === undefined || attempt === 2) return { report, artifact }
      artifact = report.revisedArtifact
    }
    throw kernelError("META_REVIEW_MODEL_PROTOCOL")
  }

  private async buildPlan(record: SessionRecord, graph: any): Promise<PlanSpec> {
    const units = Array.isArray(graph?.units) ? graph.units : []
    const basis = await hashBasis(record.workspace!, units.flatMap((unit: any) => unit.readSet ?? []))
    const planId = record.plan?.planId ?? randomUUID()
    const revision = (record.plan?.revision ?? 0) + 1
    const hackathon = record.state.skills.includes("hackathon")
    const steps = units.map((unit: any, index: number) => ({
      id: String(unit.id),
      title: String(unit.title ?? unit.id),
      claimIds: stringArray(unit.claimIds),
      criterionIds: stringArray(unit.criterionIds),
      dependsOn: stringArray(unit.dependsOn),
      readSet: stringArray(unit.readSet),
      writeSet: stringArray(unit.writeSet),
      priority: hackathon && index === 0 ? ("demo_required" as const) : ("required" as const),
    }))
    const plan: PlanSpec = {
      schemaVersion: "plan-v1",
      planId,
      revision,
      runId: record.runId!,
      domain: record.state.domain,
      skills: [...record.state.skills],
      goalContractId: "goal-" + record.contractHash!.slice(0, 16),
      goalContractRevision: record.contractRevision,
      goalContractHash: record.contractHash!,
      basis,
      steps,
      workGraph: graph,
      assumptions:
        record.preflight?.assumptions ??
        record.review?.issues
          .filter((issue) => issue.severity === "warning")
          .map((issue) => issue.statement) ?? [],
    }
    validatePlanSpec(plan)
    validatePlanCoverage(plan, requiredIDs(record.contract, "claims", "claimId"), requiredIDs(record.contract, "criteria", "criterionId"))
    return plan
  }

  private markRevalidation(
    record: SessionRecord,
    trigger: ContractRevalidationTrigger,
    affectedClaimIds: string[] = [],
    affectedCriterionIds: string[] = [],
  ) {
    const planOnly = trigger === "plan_basis_changed"
    record.state = {
      ...record.state,
      planningState: planOnly ? "plan_building" : "contract_building",
    }
    record.revisionOnly = planOnly
    record.preflight = {
      ...(record.preflight ?? emptyPreflightStatus()),
      decision: "meta_review_required",
      reasons: revalidationReasons(trigger),
      affectedClaimIds,
      affectedCriterionIds,
      mutatingActionAllowed: false,
      revalidationTrigger: trigger,
    }
  }
}

function reviewedExecutionGraph(plan: PlanSpec, original: PlanSpec): any {
  const identity = (value: PlanSpec) => ({
    schemaVersion: value.schemaVersion, planId: value.planId, revision: value.revision, runId: value.runId,
    domain: value.domain, skills: value.skills, goalContractId: value.goalContractId,
    goalContractRevision: value.goalContractRevision, goalContractHash: value.goalContractHash,
  })
  if (digest(identity(plan)) !== digest(identity(original))) throw kernelError("PLAN_IDENTITY_MISMATCH")
  const graph = plan.workGraph as { units?: unknown[] } | undefined
  if (!graph || !Array.isArray(graph.units) || graph.units.length !== plan.steps.length) {
    throw kernelError("PLAN_GRAPH_MISMATCH")
  }
  const binding = (value: any) => ({
    id: value?.id,
    claimIds: [...stringArray(value?.claimIds)].sort(),
    criterionIds: [...stringArray(value?.criterionIds)].sort(),
    dependsOn: [...stringArray(value?.dependsOn)].sort(),
    readSet: [...stringArray(value?.readSet)].sort(),
    writeSet: [...stringArray(value?.writeSet)].sort(),
  })
  if (plan.steps.some((step, index) => digest(binding(step)) !== digest(binding(graph.units![index])))) {
    throw kernelError("PLAN_GRAPH_MISMATCH")
  }
  return structuredClone(graph)
}

function contractStatus(record: SessionRecord): KernelStatus["goalContract"] {
  if (!record.contract || typeof record.contract !== "object") return undefined
  const contract = record.contract as Record<string, unknown>
  const claims = Array.isArray(contract.claims) ? contract.claims : []
  const criteria = Array.isArray(contract.criteria) ? contract.criteria : []
  return {
    revision: record.contractRevision,
    hash: record.contractHash,
    claims: claims
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      .map((claim) => ({
        id: typeof claim.claimId === "string" ? claim.claimId : "unknown",
        statement: typeof claim.statement === "string" ? claim.statement : "",
        required: claim.required !== false,
        criterionIds: stringArray(claim.criterionIds),
      })),
    criteria: criteria
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
      .map((criterion) => ({
        id: typeof criterion.criterionId === "string" ? criterion.criterionId : "unknown",
        statement: typeof criterion.statement === "string" ? criterion.statement : "",
        required: criterion.required !== false,
        risk: typeof criterion.risk === "string" ? criterion.risk : undefined,
        claimIds: stringArray(criterion.claimIds),
      })),
  }
}

function parseMetaOutput(raw: unknown, phase: MetaReviewPhase): MetaReviewReport {
  if (typeof raw !== "string") return parseMetaReview(raw, phase)
  const start = raw.indexOf("{")
  const end = raw.lastIndexOf("}")
  if (start < 0 || end < start) throw kernelError("META_REVIEW_MODEL_PROTOCOL")
  return parseMetaReview(JSON.parse(raw.slice(start, end + 1)), phase)
}

function planningSignals(contract: any, graph: any): PlanningSignals {
  const claims = Array.isArray(contract?.claims) ? contract.claims : []
  const criteria = Array.isArray(contract?.criteria) ? contract.criteria : []
  const units = Array.isArray(graph?.units) ? graph.units : []
  const targets = new Set(units.length
    ? units.flatMap((unit: any) => stringArray(unit.writeSet))
    : claims.flatMap((claim: any) => stringArray(claim.scope?.targets)))
  const riskOrder = { low: 0, medium: 1, high: 2, critical: 3 } as const
  let risk: keyof typeof riskOrder = "low"
  for (const criterion of criteria) {
    const candidate = criterion?.risk as keyof typeof riskOrder
    if (candidate in riskOrder && riskOrder[candidate] > riskOrder[risk]) risk = candidate
  }
  return {
    risk,
    requiredClaimCount: claims.filter((claim: any) => claim.required !== false).length,
    requiredCriterionCount: criteria.filter((criterion: any) => criterion.required !== false).length,
    targetCount: targets.size || 1,
    hasExternalClaim: claims.some(
      (claim: any) =>
        claim.kind === "external" || claim.external === true || claim.scope?.external === true,
    ),
    applicabilityResolved: claims.every(
      (claim: any) =>
        claim.applicability !== undefined &&
        claim.applicability?.status !== "unresolved",
    ),
    requiredEvidenceFamilyCount: Math.max(
      1,
      ...claims.map((claim: any) =>
        Number(
          claim.verifierPolicy?.minimumEvidenceFamilies ??
            claim.verifierPolicy?.minimumIndependentFamilies ??
            claim.verifierPolicy?.minIndependentFamilies ??
            1,
        ),
      ),
    ),
  }
}

function contractPreflightSignals(
  contract: unknown,
  configuredProfile: "fast" | "adaptive" | "strict",
) {
  const signals = planningSignals(contract, { units: [] })
  return {
    risk: signals.risk,
    configuredProfile,
    requiredClaimCount: signals.requiredClaimCount,
    requiredCriterionCount: signals.requiredCriterionCount,
    hasExternalClaim: signals.hasExternalClaim,
    applicabilityResolved: signals.applicabilityResolved,
  }
}

function verificationProfile(status: any): "fast" | "adaptive" | "strict" {
  const profile = status?.effectiveProfile ?? status?.configuredProfile
  return profile === "fast" || profile === "strict" ? profile : "adaptive"
}

function normalizeContractProposal(proposal: unknown): {
  contract: Record<string, unknown>
  interpretation: InterpretationProposal
} {
  if (!proposal || typeof proposal !== "object") throw kernelError("CONTRACT_SCHEMA")
  const input = proposal as Record<string, unknown>
  const interpretation = parseInterpretationProposal(
    input.interpretation,
  )
  const contract = { ...input }
  delete contract.interpretation
  return { contract, interpretation }
}

function preflightStatus(
  result: ContractPreflightResult,
  interpretation: InterpretationProposal,
  reviewerCallCount = 0,
  reviewerAssumptions: string[] = [],
): ContractPreflightStatus {
  const requiredDecisions = interpretation.candidates
    .filter((candidate) => candidate.impact !== "implementation_choice")
    .map((candidate) => ({
      id: candidate.id,
      statement: candidate.statement,
      suggestedResolution: candidate.suggestedResolution,
      impact: candidate.impact,
      affectedClaimIds: candidate.affectedClaimIds,
      affectedCriterionIds: candidate.affectedCriterionIds,
    }))
  const assumptions = [
    ...interpretation.candidates
      .filter((candidate) => candidate.impact === "implementation_choice")
      .map((candidate) => candidate.statement),
    ...reviewerAssumptions,
  ]
  return {
    ...result,
    candidateCount: interpretation.candidates.length,
    questionCount: requiredDecisions.length,
    assumptionCount: assumptions.length,
    reviewerCallCount,
    requiredDecisions,
    assumptions: [...new Set(assumptions)],
  }
}

function emptyPreflightStatus(): ContractPreflightStatus {
  return {
    version: 1,
    decision: "accept",
    reasons: [],
    affectedClaimIds: [],
    affectedCriterionIds: [],
    mutatingActionAllowed: false,
    candidateCount: 0,
    questionCount: 0,
    assumptionCount: 0,
    reviewerCallCount: 0,
    requiredDecisions: [],
    assumptions: [],
  }
}

function revalidationReasons(trigger: ContractRevalidationTrigger): PreflightReason[] {
  if (trigger === "scope_expansion_requested") return ["scope_conflict"]
  if (trigger === "applicability_changed") return ["applicability_gap"]
  if (trigger === "verifier_became_unavailable") return ["verifier_mismatch"]
  return ["complex_contract"]
}

async function hashBasis(workspace: string, paths: string[]) {
  const root = path.resolve(workspace)
  const unique = [...new Set(paths)].sort()
  const result: PlanSpec["basis"] = []
  for (const entry of unique) {
    const absolute = path.resolve(root, entry)
    if (absolute !== root && !absolute.startsWith(root + path.sep)) throw kernelError("PLAN_BASIS_ESCAPE")
    try {
      const info = await stat(absolute)
      if (!info.isFile()) continue
      result.push({
        path: path.relative(root, absolute),
        sha256: createHash("sha256").update(await readFile(absolute)).digest("hex"),
      })
    } catch (error: any) {
      if (error?.code !== "ENOENT") throw error
    }
  }
  return result
}

async function assertPlanFresh(plan: PlanSpec, workspace: string) {
  const current = await hashBasis(
    workspace,
    plan.basis.map((item) => item.path),
  )
  if (digest(current) !== digest(plan.basis)) throw kernelError("PLAN_STALE")
}

function selectionForPlan(context: unknown): PlanSelection | undefined {
  const value = context as { messageID?: string; agent?: string; extra?: {
    modelSelection?: { providerID?: string; modelID?: string }; variant?: string;
  } } | undefined
  const model = value?.extra?.modelSelection
  if (!model?.providerID || !model.modelID || !value?.messageID || !value.agent) return
  return { providerID: model.providerID, modelID: model.modelID, variant: value.extra?.variant,
    messageID: value.messageID, agent: value.agent }
}

function digest(value: unknown) {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex")
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []
}

function requiredIDs(contract: unknown, collection: string, idField: string): string[] {
  if (!contract || typeof contract !== "object") return []
  const value = (contract as Record<string, unknown>)[collection]
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .filter((item) => item.required !== false)
    .map((item) => item[idField])
    .filter((item): item is string => typeof item === "string")
}

function allIDs(contract: unknown, collection: string, idField: string): string[] {
  if (!contract || typeof contract !== "object") return []
  const value = (contract as Record<string, unknown>)[collection]
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object")
    .map((item) => item[idField])
    .filter((item): item is string => typeof item === "string")
}

function assertContractProposal(contract: unknown) {
  if (!contract || typeof contract !== "object") throw kernelError("CONTRACT_SCHEMA")
  const record = contract as Record<string, unknown>
  if (!Array.isArray(record.claims) || !Array.isArray(record.criteria)) {
    throw kernelError("CONTRACT_SCHEMA")
  }
  const claims = new Map<string, Record<string, unknown>>()
  const criteria = new Map<string, Record<string, unknown>>()
  for (const raw of record.claims) {
    if (!raw || typeof raw !== "object") throw kernelError("CONTRACT_CLAIM")
    const claim = raw as Record<string, unknown>
    if (typeof claim.claimId !== "string" || claims.has(claim.claimId)) {
      throw kernelError("CONTRACT_CLAIM_ID")
    }
    if (!Array.isArray(claim.criterionIds) || !claim.criterionIds.every((id) => typeof id === "string")) {
      throw kernelError("CONTRACT_CLAIM_CRITERIA")
    }
    claims.set(claim.claimId, claim)
  }
  for (const raw of record.criteria) {
    if (!raw || typeof raw !== "object") throw kernelError("CONTRACT_CRITERION")
    const criterion = raw as Record<string, unknown>
    if (typeof criterion.criterionId !== "string" || criteria.has(criterion.criterionId)) {
      throw kernelError("CONTRACT_CRITERION_ID")
    }
    if (!Array.isArray(criterion.claimIds) || !criterion.claimIds.every((id) => typeof id === "string")) {
      throw kernelError("CONTRACT_CRITERION_CLAIMS")
    }
    criteria.set(criterion.criterionId, criterion)
  }
  if (!claims.size || !criteria.size) throw kernelError("CONTRACT_EMPTY")
  for (const [claimId, claim] of claims) {
    for (const criterionId of claim.criterionIds as string[]) {
      const criterion = criteria.get(criterionId)
      if (!criterion || !(criterion.claimIds as string[]).includes(claimId)) {
        throw kernelError("CONTRACT_BINDING")
      }
    }
  }
  for (const [criterionId, criterion] of criteria) {
    for (const claimId of criterion.claimIds as string[]) {
      const claim = claims.get(claimId)
      if (!claim || !(claim.criterionIds as string[]).includes(criterionId)) {
        throw kernelError("CONTRACT_BINDING")
      }
    }
  }
}

function prioritizeDemoGraph(graph: any) {
  if (!Array.isArray(graph?.units) || graph.units.length < 2) return graph
  const index = graph.units.findIndex(
    (unit: any) => !Array.isArray(unit.dependsOn) || unit.dependsOn.length === 0,
  )
  if (index <= 0) return graph
  const units = [...graph.units]
  const [demo] = units.splice(index, 1)
  units.unshift(demo)
  return { ...graph, units }
}

function withPlanContext(context: unknown, plan: PlanSpec) {
  if (!context || typeof context !== "object") {
    return { planId: plan.planId, planRevision: plan.revision }
  }
  const source = context as Record<string, unknown>
  const extra =
    source.extra && typeof source.extra === "object"
      ? (source.extra as Record<string, unknown>)
      : {}
  return {
    ...source,
    planId: plan.planId,
    planRevision: plan.revision,
    extra: {
      ...extra,
      planId: plan.planId,
      planRevision: plan.revision,
    },
  }
}

function kernelError(code: string, cause?: unknown) {
  const error = new Error(code, cause === undefined ? undefined : { cause })
  error.name = "KernelError"
  ;(error as Error & { code: string }).code = code
  return error
}
