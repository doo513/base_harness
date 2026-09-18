import { collectContractAnswers, type ContractQuestionService } from "./contract-questions"
import { AutonomousHostRun, type AutonomousHostOptions } from "./autonomous-host"
import type { AutonomousCoordinatorPort, AutonomousResourceUsage, AutonomousRunSnapshot, Json, SubjectRef } from "@base-harness/domain-contracts"
export type { AutonomousHostOptions, AutonomousHostInput, StoredAutonomousSubject } from "./autonomous-host"
export type { ContractQuestionService } from "./contract-questions"
import type {
  ContractBody,
  ContractQuestionIssue,
  ContractReviewPolicy,
  DomainExecutionBinding,
  DomainExecutionModule,
  DomainExecutionModuleResolver,
  DomainExecutionOverlayModule,
  DomainExecutionProposal,
  DomainExecutorSelection,
  DomainPreparation,
  DomainRunBinding,
  HostContractContext,
  InterpretationProposal,
} from "@base-harness/domain-contracts"
import {
  allowsOperation,
  defaultContractReviewPolicy,
  applyControl,
  createKernelSessionState,
  decidePlanning,
  riskAllowsOperation,
  operationForTool,
  parseMetaReview,
  prepareContract,
  scanContract,
  validateContract,
  assertContractProposal,
  prepareContractPreflight,
  scanContractPreflight,
  validateAndDedupeContractPreflight,
  validatePlanSpec,
  validatePlanCoverage,
  type HarnessControl,
  type ContractPipelineStage,
  type ContractPreflightResult,
  type ContractRevalidationTrigger,
  type ContractValidateDedupeResult,
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
import { isDeepStrictEqual } from "node:util"
import { readFile, realpath, stat } from "node:fs/promises"
import {
  ReviewedPlanStore, type ReviewedPlanRecord, type ReviewedPlanStoreOptions,
  type PlanExecutionPolicy, type PlanSelection, type PlanRevisionClaim, type PlanDomainBinding,
} from "./reviewed-plan-store"
import path from "node:path"
import {
  SessionStateStore, sessionSelection, summarizeRun,
  type RunHistory, type SessionStateStoreOptions,
} from "./session-state-store"
// Compatibility default; the application supplies its registry explicitly.
import { builtinDomainExecutionRegistry, builtinDomainResolver, pinDomainExecutionModule, pinDomainExecutionOverlay } from "@base-harness/domain"
import type { DomainPolicy, DomainPolicySnapshot, DomainResolver, DomainSelection, ReadonlyValue } from "@base-harness/domain-contracts"

export type { RunHistory, SessionStateStoreOptions } from "./session-state-store"
export interface KernelHostOptions extends ReviewedPlanStoreOptions {
  autonomous?: AutonomousHostOptions
  domains?: DomainResolver
  domainExecutions?: DomainExecutionModuleResolver
  contractReviewPolicy?: ContractReviewPolicy
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
  contractContext?: HostContractContext
  contractClarifications?: Array<Pick<HostContractContext, "sessionID" | "runId" | "candidateRevision" | "contentHash" | "questions" | "answers">>
}

export interface KernelStatus {
  domain: KernelSessionState["domain"]
  skills: KernelSessionState["skills"]
  domainPolicy: DomainPolicy
  domainBinding?: DomainRunBinding
  domainPreparation?: DomainPreparation
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
  contractProcessing?: Omit<HostContractContext, "candidate" | "originalRequest">
  metaReview?: {
    phase: MetaReviewPhase
    outcome: MetaReviewReport["outcome"]
    issueCount: number
    blockingIssueCount: number
    issues: MetaReviewReport["issues"]
  }
}

export interface ContractPreflightStatus extends ContractPreflightResult {
  pipelineStage?: ContractPipelineStage
  scannedCandidateCount?: number
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
    sourceRefs: UncertaintyCandidate["sourceRefs"]
  }>
  assumptions: string[]
  revalidationTrigger?: ContractRevalidationTrigger
}

interface SessionRecord {
  autonomous?: AutonomousHostRun
  autonomousInputMessageIds?: Set<string>
  runEpoch?: number
  planAttempt?: object
  state: KernelSessionState
  runId?: string
  workspace?: string
  goal?: string
  context?: unknown
  contract?: unknown
  contractHash?: string
  contractRevision: number
  candidateSequence?: number
  contractContext?: HostContractContext
  contractHistory?: HostContractContext[]
  contractProcessing?: boolean
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
  domainExecutionModule?: DomainExecutionModule
  domainExecutionOverlays?: DomainExecutionOverlayModule[]
  domainBinding?: DomainRunBinding
  domainPreparation?: DomainPreparation
  pendingDomainProposal?: { runId: string; proposal: unknown; context?: unknown }
  planDomainBinding?: PlanDomainBinding
}

interface RuntimeCoordinator extends Partial<AutonomousCoordinatorPort> {
  openRun(input: any): Promise<any>
  proposeContract(sessionID: string, proposal: ContractBody): Promise<any>
  acceptWorkGraph(sessionID: string, graph: any, context?: unknown): Promise<any>
  submitDomainProposal?(input: {
    sessionID: string; runId: string; proposal: DomainExecutionProposal; context: unknown
  }): Promise<any>
  recordDomainResult?(input: {
    sessionID: string; runId: string; result: { output: string; changedFiles: string[]; adapterId: string; modelId?: string }
  }): Promise<any>
  status(sessionID: string): any
  cancel?(sessionID: string): Promise<any>
  beginPlanExecution?(sessionID: string, input: {
    planningRunId: string
    planId: string
    planRevision: number
    goalContractHash: string
    domainPolicy?: DomainPolicySnapshot
    domainBinding?: DomainExecutionBinding
    domainPreparation?: DomainPreparation
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
  private readonly autonomousOptions?: AutonomousHostOptions
  private readonly sessions = new Map<string, SessionRecord>()
  private reviewer?: (request: MetaReviewRequest) => Promise<unknown>
  private readonly listeners = new Set<(status: any) => void>()

  private readonly contractReviewPolicy: ContractReviewPolicy
  private readonly domains: DomainResolver
  private readonly domainExecutions: DomainExecutionModuleResolver
  private readonly plans: ReviewedPlanStore
  private readonly sessionStore?: SessionStateStore
  private readonly controls = new Map<string, Promise<any>>()
  private readonly executeControls = new Set<string>()
  /** Short persistence barriers only; model/reviewer waits never block a new Run. */
  private readonly planPublications = new Map<string, Promise<unknown>>()

  constructor(private readonly runtime: RuntimeCoordinator, options: KernelHostOptions = {}) {
    this.autonomousOptions = options.autonomous
    this.contractReviewPolicy = options.contractReviewPolicy ?? defaultContractReviewPolicy
    this.domains = options.domains ?? builtinDomainResolver
    this.domainExecutions = options.domainExecutions ?? builtinDomainExecutionRegistry
    this.plans = new ReviewedPlanStore(options)
    if (options.sessionState) this.sessionStore = new SessionStateStore({
      redact: options.redact,
      ...(typeof options.sessionState === "object" ? options.sessionState : {}),
      validateSelection: (selection) => { this.domains.resolve(selection) },
    })
  }

  /** Awaited Host checkpoint, not a presentation subscriber and not an actor-facing API. */
  async checkpointStatus(status: any) {
    if (!this.sessionStore || !status.runId || !status.workspace) return
    const record = this.session(status.sessionID)
    const history = summarizeRun(this.mergeStatus(status.sessionID, status))
    await this.sessionStore.save({
      sessionID: status.sessionID, workspace: status.workspace,
      selection: sessionSelection(record.state, (selection) => { this.domains.resolve(selection) }), lastRun: history,
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
      sessionID, workspace: directory, selection: sessionSelection(state, (selection) => { this.domains.resolve(selection) }), lastRun: record.history,
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
    if (record.executionStarting || record.contractProcessing) throw kernelError("RUN_ACTIVE")
    if (record.plan && planId && record.plan.planId !== planId) throw kernelError("PLAN_ID_MISMATCH")
    this.assertPlanningRunAvailable(sessionID)
    const saved = await this.plans.load({ sessionID, planId: planId ?? record.plan?.planId })
    if (await realpath(workspace) !== await realpath(saved.workspace)) throw kernelError("PLAN_WORKSPACE_MISMATCH")
    this.validateReviewedPlan(saved)
    this.assertPlanDomainCompatible(saved.state, saved.domainBinding)
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
    if (saved.domainBinding && (saved.domainBinding.schemaVersion !== "plan-domain-binding-v1"
        || !isDeepStrictEqual(saved.domainBinding.selection, {
          domain: saved.plan.domain, skills: saved.plan.skills,
        }) || saved.domainBinding.policy?.domainId !== saved.plan.domain)) {
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
      preflight: structuredClone(saved.preflight), runPolicy: saved.policy, savedPlan: saved, restored: true,
      // A recovered session already has an authoritative domain/skill selection.
      explicitSelection: true,
      revisionClaim: undefined, pendingRevision: undefined, revisionOnly: false,
      domainExecutionModule: undefined, domainExecutionOverlays: undefined,
      domainBinding: undefined, domainPreparation: undefined,
      pendingDomainProposal: undefined,
      planDomainBinding: structuredClone(saved.domainBinding),
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
      contractContext: undefined, contractHistory: undefined, candidateSequence: 0,
      domainExecutionModule: undefined, domainExecutionOverlays: undefined,
      domainBinding: undefined, domainPreparation: undefined,
      pendingDomainProposal: undefined,
      planDomainBinding: undefined,
      planAttempt: undefined,
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
            record.state = { ...createKernelSessionState(this.domains.defaultSelection), ...saved.selection }
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
      record = { state: createKernelSessionState(this.domains.defaultSelection), contractRevision: 0 }
      this.sessions.set(sessionID, record)
    }
    return record
  }

  private resolveDomainPolicy(selection: ReadonlyValue<DomainSelection>): DomainPolicy {
    // Preserve mutable wire/presentation views; the cached registry snapshot is never exposed to mutation.
    return structuredClone(this.domains.resolve(selection).policy) as DomainPolicy
  }

  private policyFor(record: SessionRecord): DomainPolicy {
    return record.domainBinding
      ? structuredClone(record.domainBinding.policy) as DomainPolicy
      : record.restored && record.planDomainBinding
      ? structuredClone(record.planDomainBinding.policy) as DomainPolicy
      : this.resolveDomainPolicy({ domain: record.state.domain, skills: record.state.skills })
  }

  private selectedExecution(state: KernelSessionState) {
    const resolved = this.domains.resolve({ domain: state.domain, skills: state.skills })
    // A resolver may return mutable registration objects. Pin callbacks with
    // their descriptors so later registrations cannot alter this Run.
    const module = pinDomainExecutionModule(this.domainExecutions.resolve(resolved.selection.domain))
    const overlays = resolved.selection.skills.map((overlayId, index) => {
      const overlay = pinDomainExecutionOverlay(this.domainExecutions.resolveOverlay(overlayId))
      if (!overlay.compatibleDomains.includes(resolved.selection.domain)
          || resolved.policy.skillRevisions[index] === undefined) {
        throw kernelError("DOMAIN_EXECUTION_OVERLAY_INCOMPATIBLE")
      }
      return overlay
    })
    const planBinding: PlanDomainBinding = {
      schemaVersion: "plan-domain-binding-v1",
      selection: structuredClone(resolved.selection) as DomainSelection,
      policy: structuredClone(resolved.policy) as DomainPolicy,
      module: { id: module.id, revision: module.revision },
      preparationStrategy: { id: module.preparation.id, revision: module.preparation.revision },
      proposalStrategy: { id: module.proposal.id, revision: module.proposal.revision },
      overlays: overlays.map((overlay, index) => ({
        overlayId: overlay.overlayId,
        overlayRevision: resolved.policy.skillRevisions[index]!,
        module: { id: overlay.id, revision: overlay.revision },
        preparationStrategy: { id: overlay.preparation.id, revision: overlay.preparation.revision },
        proposalStrategy: { id: overlay.proposal.id, revision: overlay.proposal.revision },
      })),
      skills: resolved.skills.map((skill) => ({ ...skill })),
    }
    return { module, overlays, planBinding }
  }

  private assertPlanDomainCompatible(state: KernelSessionState, saved: PlanDomainBinding | undefined) {
    if (!saved) throw kernelError("PLAN_DOMAIN_BINDING_REQUIRED")
    let current: PlanDomainBinding
    try { current = this.selectedExecution(state).planBinding } catch (error) {
      throw kernelError("PLAN_DOMAIN_BINDING_CHANGED", error)
    }
    if (!isDeepStrictEqual(current, saved)) throw kernelError("PLAN_DOMAIN_BINDING_CHANGED")
  }

  private executionSetup(record: SessionRecord, input: any): {
    module: DomainExecutionModule
    overlays: DomainExecutionOverlayModule[]
    binding: DomainExecutionBinding
    preparation: DomainPreparation
  } {
    const { module, overlays, planBinding } = this.selectedExecution(record.state)
    const executor = normalizeDomainExecutor(input?.domainExecutor, input?.execution ?? record.state.execution, input?.context)
    const { schemaVersion: _schema, skills, ...identity } = planBinding
    const binding: DomainExecutionBinding = {
      schemaVersion: "domain-execution-binding-v1", ...identity, executor: structuredClone(executor),
    }
    const environment = input?.executionEnvironment && typeof input.executionEnvironment === "object"
      ? Object.fromEntries(Object.entries(input.executionEnvironment).filter(
          (entry): entry is [string, string] => typeof entry[1] === "string",
        ))
      : {}
    const preparationInput = {
      sessionID: String(input.sessionID), workspace: String(input.workspace), goal: String(input.goal),
      selection: structuredClone(binding.selection),
      policy: structuredClone(binding.policy),
      skills: structuredClone(skills),
      executor: structuredClone(executor),
      environment: structuredClone(environment),
    }
    let preparation = module.preparation.prepare(preparationInput)
    for (const [index, overlay] of overlays.entries()) {
      preparation = overlay.preparation.apply({
        ...structuredClone(preparationInput),
        overlayId: overlay.overlayId,
        overlayRevision: binding.overlays[index]!.overlayRevision,
        preparation: structuredClone(preparation),
      })
    }
    // Knowledge selection belongs to metadata, not to an executable strategy's output.
    return { module, overlays, binding, preparation: {
      ...structuredClone(preparation), skills: structuredClone(skills),
    } }
  }

  private normalizeDomainProposal(record: SessionRecord, sessionID: string, proposal: unknown) {
    if (!record.runId || !record.domainBinding || !record.domainPreparation
        || !record.domainExecutionModule || !record.domainExecutionOverlays || !record.contract) {
      throw kernelError("DOMAIN_RUN_BINDING_INVALID")
    }
    const module = record.domainExecutionModule
    const binding = record.domainBinding
    if (binding.module.id !== module.id || binding.module.revision !== module.revision
        || binding.preparationStrategy.id !== module.preparation.id
        || binding.preparationStrategy.revision !== module.preparation.revision
        || binding.proposalStrategy.id !== module.proposal.id
        || binding.proposalStrategy.revision !== module.proposal.revision) {
      throw kernelError("DOMAIN_RUN_BINDING_INVALID")
    }
    let normalized = record.domainExecutionModule.proposal.normalize({
      sessionID, runId: record.runId, proposal: structuredClone(proposal),
      preparation: structuredClone(record.domainPreparation), binding: structuredClone(record.domainBinding),
      contract: structuredClone(record.contract) as ContractBody,
    })
    if (record.domainExecutionOverlays.length !== record.domainBinding.overlays.length) {
      throw kernelError("DOMAIN_RUN_BINDING_INVALID")
    }
    for (const [index, overlay] of record.domainExecutionOverlays.entries()) {
      const pinned = record.domainBinding.overlays[index]
      if (!pinned || pinned.overlayId !== overlay.overlayId || pinned.module.id !== overlay.id
          || pinned.module.revision !== overlay.revision
          || pinned.preparationStrategy.id !== overlay.preparation.id
          || pinned.preparationStrategy.revision !== overlay.preparation.revision
          || pinned.proposalStrategy.id !== overlay.proposal.id
          || pinned.proposalStrategy.revision !== overlay.proposal.revision) {
        throw kernelError("DOMAIN_RUN_BINDING_INVALID")
      }
      normalized = overlay.proposal.apply({
        sessionID,
        runId: record.runId,
        overlayId: pinned.overlayId,
        overlayRevision: pinned.overlayRevision,
        proposal: structuredClone(normalized),
        preparation: structuredClone(record.domainPreparation),
        binding: structuredClone(record.domainBinding),
        contract: structuredClone(record.contract) as ContractBody,
      })
    }
    return structuredClone(normalized)
  }

  private assertPlanningRunAvailable(sessionID: string, status = this.runtime.status(sessionID)) {
    if (["blocked", "interrupted", "failure"].includes(status?.phase) || status?.outcome === "failure") {
      throw kernelError("PLAN_RUN_BLOCKED")
    }
  }

  private runGuard(sessionID: string, code: string) {
    const record = this.session(sessionID)
    const runId = record.runId, epoch = record.runEpoch
    return () => {
      const current = this.runtime.status(sessionID)
      if (!runId || this.sessions.get(sessionID) !== record || record.runId !== runId
          || record.runEpoch !== epoch || current.runId !== runId
          || ["inactive", "interrupted"].includes(current.phase)) throw kernelError(code)
      this.assertPlanningRunAvailable(sessionID, current)
    }
  }

  private async publishPlan<T>(sessionID: string, publish: () => Promise<T>): Promise<T> {
    const operation = Promise.resolve().then(publish)
    this.planPublications.set(sessionID, operation)
    try { return await operation } finally {
      if (this.planPublications.get(sessionID) === operation) this.planPublications.delete(sessionID)
    }
  }

  async openRun(input: any) {
    if (input.semantics !== undefined && !["legacy", "autonomous-v1"].includes(input.semantics)) throw kernelError("RUN_SEMANTICS_UNSUPPORTED")
    if (input.semantics === "autonomous-v1") return this.openAutonomousRun(input)
    if (this.runtime.status(input.sessionID)?.autonomous?.lifecycle &&
        this.runtime.status(input.sessionID).autonomous.lifecycle !== "closed") {
      if (input.semantics && input.semantics !== "autonomous-v1") throw kernelError("RUN_SEMANTICS_FIXED")
      return this.openAutonomousRun(input)
    }
    while (this.planPublications.has(input.sessionID)) await this.planPublications.get(input.sessionID)!.catch(() => undefined)
    if (!this.runtime.isInternalContinuation?.(input.sessionID)) await this.controls.get(input.sessionID)
    await this.readStatus(input.sessionID, input.workspace)
    // A publication can start while the preceding reads are awaiting I/O.
    while (this.planPublications.has(input.sessionID)) await this.planPublications.get(input.sessionID)!.catch(() => undefined)
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
    if (record.executionStarting || record.contractProcessing) throw kernelError("RUN_ACTIVE")
    record.runEpoch = (record.runEpoch ?? 0) + 1
    record.planAttempt = undefined
    record.executionStarting = true
    try {
      if (["ready", "blocked", "interrupted"].includes(this.runtime.status(input.sessionID)?.phase)
          && !record.revisionClaim && record.state.planningState !== "plan_ready") {
        const preference = record.state.planningPreference
        this.clearReviewedPlan(record)
        record.state.planningPreference = preference
      }
      if (!record.runId && !record.explicitSelection && input.defaultDomain) {
        record.state = { ...record.state, ...this.domains.normalizeSelection(
          { domain: record.state.domain, skills: record.state.skills },
          { type: "domain.set", domain: input.defaultDomain },
        ) }
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
      const currentRuntime = this.runtime.status(input.sessionID)
      const reuseBinding = !!record.domainBinding && !!record.domainExecutionModule
        && !!record.domainExecutionOverlays && !!record.domainPreparation
        && !!record.runId && currentRuntime.runId === record.runId
        && !["ready", "blocked", "failure", "interrupted", "inactive"].includes(currentRuntime.phase)
      const setup = reuseBinding ? {
        module: record.domainExecutionModule!,
        overlays: record.domainExecutionOverlays!,
        binding: (() => {
          const { runId: _runId, ...binding } = structuredClone(record.domainBinding!)
          return binding
        })(),
        preparation: structuredClone(record.domainPreparation!),
      } : this.executionSetup(record, input)
      // Keep the selected execution backend in the Kernel session state before
      // the first status read. Without this, TUI prompts temporarily use the
      // external model marker but the follow-up status falls back to the
      // ordinary Provider loop and reports a fake external model as missing.
      record.state = { ...record.state, execution: reuseBinding ? record.state.execution : input.execution }
      record.restored = false
      record.workspace = input.workspace
      record.goal = input.goal
      record.context = input.context
      const previousRunId = record.runId
      const result = await this.runtime.openRun({
        ...input,
        revisesPlan,
        execution: record.state.execution,
        domainPolicy: structuredClone(setup.binding.policy),
        domainBinding: structuredClone(setup.binding),
        domainPreparation: structuredClone(setup.preparation),
      })
      record.runId = result.runId
      if (!reuseBinding || previousRunId !== result.runId) {
        record.domainExecutionModule = setup.module
        record.domainExecutionOverlays = [...setup.overlays]
        record.domainBinding = { ...structuredClone(setup.binding), runId: result.runId }
        record.domainPreparation = structuredClone(setup.preparation)
        record.planDomainBinding = planDomainBinding(setup.binding, setup.preparation)
        record.pendingDomainProposal = undefined
      }
      record.contractContext = undefined
      record.contractHistory = []
      record.candidateSequence = 0
      if (record.preflight) record.preflight.mutatingActionAllowed = false
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

  private autonomousRuntime(): AutonomousCoordinatorPort {
    const names: Array<keyof AutonomousCoordinatorPort> = ["autonomousBasis", "prepareAutonomous", "resumeAutonomous", "reviseAutonomousIntent", "submitAutonomousDecision",
      "reserveAutonomousModel", "settleAutonomousModel", "registerAutonomousSubject", "registerAutonomousCheck"]
    if (names.some((name) => typeof this.runtime[name] !== "function")) throw kernelError("AUTONOMOUS_RUNTIME_UNAVAILABLE")
    return this.runtime as RuntimeCoordinator & AutonomousCoordinatorPort
  }

  private autonomousSession(sessionID: string, runId: string) {
    const record = this.session(sessionID)
    if (!record.autonomous || record.runId !== runId || this.runtime.status(sessionID)?.runId !== runId) throw kernelError("AUTONOMOUS_RUN_MISMATCH")
    return record.autonomous
  }

  private async openAutonomousRun(input: any) {
    if (!this.autonomousOptions) throw kernelError("AUTONOMOUS_EXECUTION_NOT_CONFIGURED")
    const runtime = this.autonomousRuntime()
    await this.controls.get(input.sessionID)
    await this.readStatus(input.sessionID, input.workspace)
    const record = this.session(input.sessionID)
    if (record.executionStarting || record.contractProcessing || record.pendingRevision) throw kernelError("RUN_ACTIVE")
    if (record.state.planningPreference === "plan_once" || record.state.planningState === "plan_ready" || input.planOnly) {
      throw kernelError("AUTONOMOUS_PLAN_EXECUTION_UNSUPPORTED")
    }
    const current = this.runtime.status(input.sessionID)
    if (current.autonomous && current.autonomous.lifecycle !== "closed") {
      if (!record.autonomous || record.runId !== current.runId || record.workspace !== input.workspace) throw kernelError("AUTONOMOUS_RUN_MISMATCH")
      const messageId = input.context && typeof input.context === "object" && typeof input.context.messageID === "string"
        ? input.context.messageID : undefined
      if (!messageId) throw kernelError("AUTONOMOUS_USER_REVISION_SOURCE")
      record.autonomousInputMessageIds ??= new Set()
      if (!record.autonomousInputMessageIds.has(messageId)) {
        record.autonomousInputMessageIds.add(messageId)
        try { await record.autonomous.appendUserRequest(String(input.goal), input.context) }
        catch (error) { record.autonomousInputMessageIds.delete(messageId); throw error }
      }
      return this.emitStatus(input.sessionID, this.runtime.status(input.sessionID))
    }
    record.executionStarting = true
    let created: Awaited<ReturnType<typeof AutonomousHostRun.create>> | undefined
    try {
      if (!record.runId && !record.explicitSelection && input.defaultDomain) {
        record.state = { ...record.state, ...this.domains.normalizeSelection({ domain: record.state.domain, skills: record.state.skills },
          { type: "domain.set", domain: input.defaultDomain }) }
      }
      const domain = this.domains.resolve({ domain: record.state.domain, skills: record.state.skills })
      const executor = normalizeDomainExecutor(input.domainExecutor, input.execution ?? record.state.execution, input.context)
      const opened = await this.runtime.openRun({ sessionID: input.sessionID, workspace: input.workspace, goal: input.goal,
        context: input.context, execution: input.execution,
        autonomousFactory: async (runId: string) => {
          created = await AutonomousHostRun.create({ sessionID: input.sessionID, runId, workspace: input.workspace, goal: input.goal,
            domainId: domain.selection.domain,
            domainSnapshot: JSON.parse(JSON.stringify({ selection: domain.selection, policy: domain.policy })) as Json,
            executor, context: input.context }, this.autonomousOptions!, runtime, () => {
              const snapshot = this.runtime.status(input.sessionID).autonomous as AutonomousRunSnapshot | undefined
              if (!snapshot || snapshot.binding.runId !== runId) throw kernelError("AUTONOMOUS_RUN_MISMATCH")
              return snapshot
            })
          return { setup: created.setup, ports: created.ports }
        },
      })
      if (!created || opened.runId !== created.setup.binding.runId || !opened.autonomous || opened.failureKind) {
        throw kernelError("AUTONOMOUS_RUN_OPEN_FAILED")
      }
      record.autonomous = created.host
      const messageId = input.context && typeof input.context === "object" && typeof input.context.messageID === "string"
        ? input.context.messageID : undefined
      record.autonomousInputMessageIds = new Set(messageId ? [messageId] : [])
      record.runId = opened.runId
      record.workspace = input.workspace
      record.goal = input.goal
      record.context = input.context
      record.contract = undefined
      record.contractHash = undefined
      record.contractRevision = 0
      record.domainBinding = undefined
      record.domainPreparation = undefined
      record.preflight = undefined
      record.review = undefined
      record.state = { ...record.state, execution: input.execution, planningState: "executing" }
      const prepared = await created.host.prepare()
      record.state.planningState = prepared.status === "needs_input" ? "awaiting_input" : "executing"
      return this.emitStatus(input.sessionID, this.runtime.status(input.sessionID))
    } catch (error) {
      if (created) {
        await this.runtime.cancel?.(input.sessionID).catch(() => undefined)
        await created.ports.cleanup().catch(() => undefined)
      }
      throw error
    } finally { record.executionStarting = false }
  }

  async submitAutonomousDecision(sessionID: string, runId: string, decisionId: string, response: unknown) {
    const result = await this.autonomousSession(sessionID, runId).submit(decisionId, response)
    const record = this.session(sessionID)
    if (record.runId === runId) {
      const state = this.runtime.status(sessionID).autonomous as AutonomousRunSnapshot
      record.state.planningState = state.lifecycle === "waiting_input" ? "awaiting_input" : state.lifecycle === "closed" ? "idle" : "executing"
      this.emitStatus(sessionID, this.runtime.status(sessionID))
    }
    return result
  }

  captureAutonomousSource(sessionID: string, runId: string, bytes: Uint8Array, origin: string) {
    return this.autonomousSession(sessionID, runId).captureSource(bytes, origin)
  }

  async requestAutonomousAnswers(sessionID: string, runId: string) {
    const prepared = await this.autonomousSession(sessionID, runId).requestAnswers()
    const record = this.session(sessionID)
    if (record.runId === runId) {
      record.state.planningState = prepared.status === "needs_input" ? "awaiting_input" : "executing"
      this.emitStatus(sessionID, this.runtime.status(sessionID))
    }
    return prepared
  }

  proposeAutonomousCheck(sessionID: string, runId: string, subject: SubjectRef, parameters: Json) {
    return this.autonomousSession(sessionID, runId).proposeCheck(subject, parameters)
  }

  reserveAutonomousModel(sessionID: string, runId: string, requestId: string, payload: Json, upperBound: AutonomousResourceUsage) {
    return this.autonomousSession(sessionID, runId).reserveModel(requestId, payload, upperBound)
  }

  settleAutonomousModel(sessionID: string, runId: string, requestId: string, usage: AutonomousResourceUsage) {
    return this.autonomousSession(sessionID, runId).settleModel(requestId, usage)
  }

  private runContractPipeline(
    record: SessionRecord,
    proposal: unknown,
    policy: DomainPolicy,
    configuredProfile: "fast" | "adaptive" | "strict",
  ): { normalized: NormalizedContractProposal; analysis: ContractValidateDedupeResult } {
    record.state = { ...record.state, planningState: "contract_preparing" }
    const prepared = prepareContract(proposal, policy, configuredProfile)
    record.state = { ...record.state, planningState: "contract_scanning" }
    const scanned = scanContract(prepared)
    record.state = { ...record.state, planningState: "contract_validate_dedupe" }
    const structure = validateContract(scanned)
    if (!structure.valid) {
      const error = kernelError(structure.diagnostics[0]!.code)
      Object.assign(error, { diagnostics: structure.diagnostics })
      throw error
    }
    const normalized = { contract: structure.candidate.body, interpretation: structure.candidate.interpretation }
    const analysis = validateAndDedupeContractPreflight(scanContractPreflight(
      prepareContractPreflight(normalized.interpretation, structure.signals),
    ), this.contractReviewPolicy)
    return { normalized, analysis }
  }

  private captureContractCandidate(sessionID: string, record: SessionRecord, normalized: NormalizedContractProposal) {
    if (record.contractContext) (record.contractHistory ??= []).push(structuredClone(record.contractContext))
    const candidate = { body: structuredClone(normalized.contract), interpretation: structuredClone(normalized.interpretation) }
    record.contractContext = {
      sessionID, runId: record.runId!, originalRequest: record.goal ?? "",
      candidateRevision: record.candidateSequence = (record.candidateSequence ?? 0) + 1,
      contentHash: digest(candidate), candidate, outcome: "checking", issues: [], questions: [], answers: [],
    }
  }

  private waitForContractInput(record: SessionRecord, review?: MetaReviewReport) {
    const issues: ContractQuestionIssue[] = (record.preflight?.requiredDecisions ?? []).map((issue) => ({
      ...structuredClone(issue), id: `interpretation:${issue.id}`,
    }))
    const candidate = record.contractContext!.candidate
    for (const issue of review?.issues ?? []) if (issue.severity === "blocking") issues.push({
      id: `review:${issue.id}`, statement: issue.statement, suggestedResolution: issue.suggestedResolution,
      sourceRefs: structuredClone(issue.sourceRefs),
      affectedClaimIds: issue.targetIds.filter((id) => candidate.body.claims.some((claim) => claim.claimId === id)),
      affectedCriterionIds: issue.targetIds.filter((id) => candidate.body.criteria.some((criterion) => criterion.criterionId === id)),
    })
    record.contractContext!.issues = issues
    record.contractContext!.outcome = "needs_input"
    record.state = { ...record.state, planningState: "awaiting_input" }
    if (record.preflight) record.preflight.mutatingActionAllowed = false
  }

  async requestContractQuestions(sessionID: string, ask: ContractQuestionService, signal?: AbortSignal) {
    const record = this.session(sessionID)
    const context = record.contractContext
    if (!context || context.outcome !== "needs_input") return this.status(sessionID)
    const revision = context.candidateRevision, hash = context.contentHash, runId = context.runId
    try {
      await collectContractAnswers(context, ask, () => {
        const current = this.runtime.status(sessionID)
        return !signal?.aborted && this.session(sessionID) === record
          && !record.executionStarting && !record.contractProcessing
          && record.contractContext === context && record.runId === runId
          && current.runId === runId && context.sessionID === sessionID
          && !["inactive", "blocked", "interrupted", "failure"].includes(current.phase) && current.outcome !== "failure"
          && context.candidateRevision === revision && context.contentHash === hash
      }, () => {
        if (context.outcome === "revision_required") record.state = { ...record.state, planningState: "contract_building" }
        this.emitStatus(sessionID, this.runtime.status(sessionID))
      })
    } catch (error) {
      if (record.contractContext === context && !["CONTRACT_ANSWER_STALE", "CONTRACT_QUESTION_ACTIVE"].includes((error as { code?: string }).code ?? "")) {
        context.outcome = "error"
        record.state = { ...record.state, planningState: "contract_building" }
        this.emitStatus(sessionID, this.runtime.status(sessionID))
      }
      throw error
    }
    return this.status(sessionID)
  }

  async proposeContract(sessionID: string, proposal: unknown, context?: unknown) {
    while (this.planPublications.has(sessionID)) await this.planPublications.get(sessionID)!.catch(() => undefined)
    const record = this.session(sessionID)
    if (record.contractProcessing || record.executionStarting) throw kernelError("CONTRACT_PROCESSING_ACTIVE")
    if (!record.runId || record.runId !== this.runtime.status(sessionID).runId) throw kernelError("CONTRACT_RUN_UNAVAILABLE")
    this.assertPlanningRunAvailable(sessionID)
    if (context) record.context = context
    record.contractProcessing = true
    record.review = undefined
    record.preflight = emptyPreflightStatus()
    record.state = { ...record.state, planningState: "contract_building" }
    // Immediately invalidate outstanding questions, even if the new candidate is malformed.
    if (record.contractContext) (record.contractHistory ??= []).push(structuredClone(record.contractContext))
    record.contractContext = undefined
    const runId = record.runId
    try {
      const policy = this.policyFor(record)
      let pipeline = this.runContractPipeline(record, proposal, policy, verificationProfile(this.runtime.status(sessionID)))
      this.captureContractCandidate(sessionID, record, pipeline.normalized)
      record.preflight = preflightStatus(pipeline.analysis)
      if (pipeline.analysis.result.decision === "needs_input") {
        this.waitForContractInput(record)
        return this.emitStatus(sessionID, this.runtime.status(sessionID))
      }
      if (pipeline.analysis.result.decision === "meta_review_required") {
        record.contractContext!.outcome = "reviewing"
        const reviewed = await this.review(sessionID, "goal_contract", {
          ...pipeline.normalized.contract, interpretation: pipeline.normalized.interpretation,
        }, (revised) => {
          const reviewerCalls = record.preflight?.reviewerCallCount ?? 0
          pipeline = this.runContractPipeline(record, revised, policy, verificationProfile(this.runtime.status(sessionID)))
          this.captureContractCandidate(sessionID, record, pipeline.normalized)
          record.preflight = preflightStatus(pipeline.analysis, reviewerCalls)
        })
        if (reviewed.report.outcome === "needs_input") {
          this.waitForContractInput(record, reviewed.report)
          return this.emitStatus(sessionID, this.runtime.status(sessionID))
        }
        if (reviewed.report.outcome === "revise") {
          record.contractContext!.outcome = "revision_required"
          record.state = { ...record.state, planningState: "contract_building" }
          return this.emitStatus(sessionID, this.runtime.status(sessionID))
        }
        const checkedDecision: ContractPreflightResult = pipeline.analysis.result
        if (checkedDecision.decision === "needs_input") {
          this.waitForContractInput(record)
          return this.emitStatus(sessionID, this.runtime.status(sessionID))
        }
        record.preflight = preflightStatus(pipeline.analysis, record.preflight?.reviewerCallCount ?? 0,
          reviewed.report.issues.filter((issue) => issue.severity === "warning").map((issue) => issue.statement),
          { ...pipeline.analysis.result, decision: "accept", mutatingActionAllowed: false })
      }
      record.contractContext!.outcome = "awaiting_runtime"
      record.preflight!.mutatingActionAllowed = false
      const runtimeResult = await this.runtime.proposeContract(sessionID, structuredClone(pipeline.normalized.contract))
      if (record.runId !== runId || this.runtime.status(sessionID).runId !== runId) throw kernelError("CONTRACT_RUN_CHANGED")
      if (runtimeResult.contractStatus !== "accepted") {
        record.contractContext!.outcome = "rejected"
        record.state = { ...record.state, planningState: "contract_building" }
        return this.emitStatus(sessionID, runtimeResult)
      }
      if (runtimeResult.runId !== runId) throw kernelError("CONTRACT_RUN_CHANGED")
      this.assertPlanningRunAvailable(sessionID, runtimeResult)
      record.preflight!.mutatingActionAllowed = true
      record.contractContext!.outcome = "accepted"
      record.contract = structuredClone(pipeline.normalized.contract)
      record.contractRevision += 1
      record.contractHash = digest(record.contract)
      record.decision = record.revisionOnly ? "planned" : decidePlanning(record.state, planningSignals(record.contract, undefined, policy))
      record.state = { ...record.state, planningState: record.decision === "direct" ? "executing" : "planning_decision" }
      if (record.decision === "direct") this.runtime.beginDirect?.(sessionID)
      else this.runtime.beginPlanning?.(sessionID)
      if (record.decision === "direct" && !record.pendingDomainProposal) {
        record.pendingDomainProposal = {
          runId,
          proposal: { kind: "direct", dispatch: "attached", instruction: record.goal ?? pipeline.normalized.contract.goal },
          context: record.context,
        }
      }
      const pendingKind = record.pendingDomainProposal?.proposal
        && typeof record.pendingDomainProposal.proposal === "object"
        ? (record.pendingDomainProposal.proposal as { kind?: unknown }).kind
        : undefined
      // A direct proposal cannot manufacture a reviewed plan. In plan-only mode
      // it remains staged and, critically, is not executed.
      if (record.pendingDomainProposal && (record.decision === "direct" || pendingKind === "work_graph")) {
        return await this.dispatchPendingDomainProposal(sessionID)
      }
      return this.emitStatus(sessionID, runtimeResult)
    } catch (error) {
      const failedContext = this.session(sessionID).contractContext
      if (failedContext) failedContext.outcome = "error"
      if (record.preflight) record.preflight.mutatingActionAllowed = false
      record.state = { ...record.state, planningState: "contract_building" }
      this.emitStatus(sessionID, this.runtime.status(sessionID))
      throw error
    } finally {
      record.contractProcessing = false
    }
  }

  async stageExecutionProposal(sessionID: string, proposal: unknown, context?: unknown) {
    const record = this.session(sessionID)
    const current = this.runtime.status(sessionID)
    if (!record.runId || record.runId !== current.runId || !record.domainBinding
        || record.domainBinding.runId !== current.runId) throw kernelError("DOMAIN_RUN_MISMATCH")
    this.assertPlanningRunAvailable(sessionID, current)
    record.pendingDomainProposal = {
      runId: record.runId,
      proposal: structuredClone(proposal),
      ...(context !== undefined ? { context } : {}),
    }
    if (context !== undefined) record.context = context
    return this.status(sessionID)
  }

  async acceptExecutionProposal(sessionID: string, proposal: unknown, context?: unknown) {
    const assertCurrent = this.runGuard(sessionID, "DOMAIN_RUN_MISMATCH")
    await this.stageExecutionProposal(sessionID, proposal, context)
    assertCurrent()
    if (!this.hasAcceptedContract(sessionID)) throw kernelError("CONTRACT_REQUIRED")
    return this.dispatchPendingDomainProposal(sessionID)
  }

  private async dispatchPendingDomainProposal(sessionID: string) {
    const record = this.session(sessionID)
    const pending = record.pendingDomainProposal
    if (!pending) return this.status(sessionID)
    if (!this.hasAcceptedContract(sessionID) || !record.runId || pending.runId !== record.runId
        || !record.domainBinding || record.domainBinding.runId !== record.runId
        || !record.domainPreparation || !record.domainExecutionModule
        || !record.domainExecutionOverlays || !record.contract) {
      throw kernelError("CONTRACT_REQUIRED")
    }
    const normalized = this.normalizeDomainProposal(record, sessionID, pending.proposal)
    record.pendingDomainProposal = undefined
    const proposalContext = pending.context ?? record.context
    if (normalized.kind === "work_graph") {
      return this.acceptNormalizedWorkGraph(sessionID, normalized.graph, proposalContext)
    }
    const enteringDirect = record.state.planningState !== "executing"
    record.state = { ...record.state, planningState: "executing" }
    if (enteringDirect) this.runtime.beginDirect?.(sessionID)
    if (!this.runtime.submitDomainProposal) return this.emitStatus(sessionID, this.runtime.status(sessionID))
    const runId = record.runId
    const result = await this.runtime.submitDomainProposal({
      sessionID, runId, proposal: normalized, context: proposalContext,
    })
    if (record.runId !== runId || result.runId !== runId || this.runtime.status(sessionID).runId !== runId) {
      throw kernelError("DOMAIN_RUN_MISMATCH")
    }
    return this.emitStatus(sessionID, result)
  }

  async acceptWorkGraph(sessionID: string, graph: any, context?: unknown) {
    return this.acceptExecutionProposal(sessionID, { kind: "work_graph", graph }, context)
  }

  private async acceptNormalizedWorkGraph(sessionID: string, graph: any, context?: unknown) {
    const assertAdmission = this.runGuard(sessionID, "PLAN_RUN_CHANGED")
    while (this.planPublications.has(sessionID)) await this.planPublications.get(sessionID)!.catch(() => undefined)
    assertAdmission()
    const record = this.session(sessionID)
    if (context) record.context = context
    record.graphContext = context
    if (!this.hasAcceptedContract(sessionID) || !record.workspace || !record.runId) {
      throw kernelError("CONTRACT_REQUIRED")
    }
    this.assertPlanningRunAvailable(sessionID)
    const runId = record.runId
    const epoch = record.runEpoch
    const contractHash = record.contractHash, contractRevision = record.contractRevision
    const contractContext = record.contractContext
    const attempt = record.planAttempt = {}
    const assertRun = this.runGuard(sessionID, "PLAN_RUN_CHANGED")
    const assertCurrent = () => {
      assertRun()
      if (record.planAttempt !== attempt || record.contractHash !== contractHash
          || record.contractRevision !== contractRevision || record.contractContext !== contractContext) {
        throw kernelError("PLAN_RUN_CHANGED")
      }
    }
    const policy = this.policyFor(record)
    const executionGraph = structuredClone(graph)
    const decision = record.revisionOnly || record.state.execution?.kind === "agent_runtime"
      ? "planned"
      : decidePlanning(record.state, planningSignals(record.contract, executionGraph, policy))
    record.decision = decision
    if (decision === "direct" && record.state.planningPreference !== "plan_once") {
      record.state = { ...record.state, planningState: "executing" }
      this.runtime.beginDirect?.(sessionID)
      return this.emitStatus(sessionID, this.runtime.status(sessionID))
    }

    this.runtime.beginPlanning?.(sessionID)
    record.state = { ...record.state, planningState: "plan_building" }
    const plan = await this.buildPlan({ ...record,
      state: structuredClone(record.state), contract: structuredClone(record.contract),
      preflight: structuredClone(record.preflight), review: structuredClone(record.review),
    }, executionGraph)
    assertCurrent()
    record.state = { ...record.state, planningState: "plan_reviewing" }
    const reviewed = await this.review(sessionID, "plan", plan, undefined, assertCurrent)
    assertCurrent()
    if (reviewed.report.outcome !== "pass") {
      record.state = { ...record.state, planningState: reviewed.report.outcome === "needs_input" ? "awaiting_input" : "plan_building" }
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
    assertCurrent()
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
      domainBinding: structuredClone(record.planDomainBinding),
      selection: selectionForPlan(context),
    }
    await this.publishPlan(sessionID, async () => {
      let published: ReviewedPlanRecord | undefined
      try {
        assertCurrent()
        published = await this.plans.save(saved, record.revisionClaim)
        assertCurrent()
        if (!planOnly) {
          await this.plans.consume(published, "execute")
          assertCurrent()
        }
        record.savedPlan = planOnly ? published : undefined
        record.revisionClaim = undefined
        record.pendingRevision = undefined
        record.revisionOnly = false
        record.graph = reviewedGraph
        record.plan = canonical
        record.graphContext = withPlanContext(context, canonical)
        record.state = planState
        if (planOnly) {
          await this.checkpointStatus(this.runtime.status(sessionID))
          assertCurrent()
        }
      } catch (error) {
        let obsolete: unknown
        try { assertCurrent() } catch (failure) { obsolete = failure }
        if (obsolete) {
          // Publication may have finished while cancellation was in flight.
          // Retire that exact old plan before admitting the next local Run.
          if (published) await this.plans.consume(published, "discard").catch((failure) => {
            if (failure?.code !== "PLAN_ALREADY_CONSUMED") throw failure
          })
          if (record.runId === runId && record.runEpoch === epoch && record.planAttempt === attempt) {
            if (!published && record.revisionClaim) {
              record.pendingRevision = record.revisionClaim.record
              record.state = { ...record.state, planningState: "awaiting_input" }
            } else this.clearReviewedPlan(record)
          }
          throw obsolete
        }
        record.pendingRevision = record.revisionClaim?.record
        record.state = { ...record.state, planningState: "awaiting_input" }
        await this.runtime.reportMetaReviewFailure?.(sessionID, error, "plan_persistence", "harness")
        this.emitStatus(sessionID, this.runtime.status(sessionID))
        throw error
      }
    })
    assertCurrent()
    if (planOnly) return this.emitStatus(sessionID, this.runtime.status(sessionID))
    const dispatched = this.runtime.submitDomainProposal
      ? await this.runtime.submitDomainProposal({
          sessionID, runId,
          proposal: { kind: "work_graph", graph: reviewedGraph }, context: record.graphContext,
        })
      : await this.runtime.acceptWorkGraph(sessionID, reviewedGraph, record.graphContext)
    assertCurrent()
    return this.emitStatus(sessionID, dispatched)
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
    while (this.planPublications.has(sessionID)) await this.planPublications.get(sessionID)!.catch(() => undefined)
    await this.readStatus(sessionID, workspace)
    while (this.planPublications.has(sessionID)) await this.planPublications.get(sessionID)!.catch(() => undefined)
    const record = this.session(sessionID)
    const selectionWorkspace = workspace ?? record.workspace ?? record.historyWorkspace
    if (record.executionStarting || record.contractProcessing) throw kernelError("RUN_ACTIVE")
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
        this.assertPlanDomainCompatible(record.state, record.planDomainBinding)
        if (context) record.graphContext = withPlanContext(context, record.plan)
        const planningRunId = record.runId!
        const setup = record.domainBinding && record.domainExecutionModule
          && record.domainExecutionOverlays && record.domainPreparation
          ? {
              module: record.domainExecutionModule,
              overlays: record.domainExecutionOverlays,
              binding: (() => {
                const { runId: _runId, ...binding } = structuredClone(record.domainBinding!)
                return binding
              })(),
              preparation: structuredClone(record.domainPreparation),
            }
          : this.executionSetup(record, {
              sessionID, workspace: record.workspace, goal: record.goal,
              execution: record.state.execution, context: record.graphContext,
            })
        const checked = this.normalizeDomainProposal({
          ...record,
          domainExecutionModule: setup.module,
          domainExecutionOverlays: setup.overlays,
          domainBinding: { ...setup.binding, runId: planningRunId },
          domainPreparation: setup.preparation,
        }, sessionID, { kind: "work_graph", graph: structuredClone(record.graph) })
        if (checked.kind !== "work_graph" || !isDeepStrictEqual(checked.graph, record.graph)) {
          throw kernelError("PLAN_EXECUTION_GRAPH_CHANGED")
        }
        if (record.savedPlan) await this.plans.consume(record.savedPlan, "execute")
        record.savedPlan = undefined
        handoffStarted = true
        // Keep mutation and completion disabled while the new verifier accepts the same contract.
        record.state = { ...record.state, planningState: "plan_building" }
        this.emitStatus(sessionID, this.runtime.status(sessionID))
        const input = {
          planningRunId, planId: record.plan.planId, planRevision: record.plan.revision,
          goalContractHash: record.plan.goalContractHash, context: record.graphContext,
          execution: record.state.execution,
          domainPolicy: structuredClone(setup.binding.policy),
          domainBinding: structuredClone(setup.binding),
          domainPreparation: structuredClone(setup.preparation),
        }
        const execution = record.restored
          ? await this.runtime.beginRestoredPlanExecution!(sessionID, {
              ...input, ...record.runPolicy, workspace: record.workspace, goal: record.goal, contract: record.contract,
            })
          : await this.runtime.beginPlanExecution!(sessionID, input)
        record.restored = false
        record.runId = execution.runId
        record.domainExecutionModule = setup.module
        record.domainExecutionOverlays = [...setup.overlays]
        record.domainBinding = { ...structuredClone(setup.binding), runId: execution.runId }
        record.domainPreparation = structuredClone(setup.preparation)
        if (!record.runId || record.runId === planningRunId) throw kernelError("PLAN_EXECUTION_RUN_INVALID")
        if (execution.contractStatus !== "accepted" || ["blocked", "failure"].includes(execution.phase)
            || ["repair", "blocked", "failure", "needs_input", "repair_exhausted"].includes(execution.outcome)) {
          record.state = { ...record.state, planningState: "awaiting_input" }
          return this.emitStatus(sessionID, execution)
        }
        record.state = { ...record.state, planningState: "executing" }
        const proposal = this.normalizeDomainProposal(
          record,
          sessionID,
          { kind: "work_graph", graph: structuredClone(record.graph) },
        )
        if (proposal.kind !== "work_graph" || !isDeepStrictEqual(proposal.graph, record.graph)) {
          throw kernelError("PLAN_EXECUTION_GRAPH_CHANGED")
        }
        if (this.runtime.submitDomainProposal) {
          await this.runtime.submitDomainProposal({ sessionID, runId: record.runId, proposal, context: record.graphContext })
        } else {
          await this.runtime.acceptWorkGraph(sessionID, proposal.graph, record.graphContext)
        }
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
    // Validate before consuming a saved plan or persisting selection changes.
    const nextSelection = control.type === "domain.set" || control.type === "skill.set"
      ? this.domains.normalizeSelection({ domain: record.state.domain, skills: record.state.skills }, control)
      : undefined
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
    const selected = nextSelection ? { ...record.state, ...nextSelection } : applyControl(record.state, control)
    await this.persistSelection(sessionID, selected, selectionWorkspace)
    record.state = selected
    if (control.type === "domain.set" || control.type === "skill.set") record.explicitSelection = true
    return this.emitStatus(sessionID, this.runtime.status(sessionID))
  }

  assertToolAllowed(
    sessionID: string, toolID: string, subagentType?: string,
    hostOperation?: ToolOperation,
  ) {
    const status = this.runtime.status(sessionID)
    const rootSessionID = status.sessionID ?? sessionID
    const record = this.session(rootSessionID)
    const operation = hostOperation ?? operationForTool(toolID)
    if (status.autonomous) {
      if (!record.autonomous || record.runId !== status.runId) throw kernelError("AUTONOMOUS_RUN_MISMATCH")
      if (!["read", "search", "execute"].includes(operation)) throw kernelError("AUTONOMOUS_CAPABILITY_UNSUPPORTED")
      record.autonomous.assertInvocation(toolID, operation)
      return
    }
    const policy = this.policyFor(record)
    if (operation === "unknown" && !policy.allowedOperations.includes(operation as never)) {
      throw kernelError("DOMAIN_PERMISSION_UNKNOWN")
    }
    if (!allowsOperation(record.state, operation, subagentType, policy)) {
      throw kernelError(
        policy.allowedOperations.includes(operation as never)
          ? "PLAN_ONLY_MUTATION_DENIED"
          : "DOMAIN_PERMISSION_DENIED",
      )
    }
    const requiresContract = operation === "mutate" || operation === "execute"
      || (operation === "delegate" && subagentType !== "explore" && subagentType !== "meta-review")
    if (requiresContract) {
      if (!this.hasAcceptedContract(rootSessionID)) throw kernelError("CONTRACT_REQUIRED")
      const acceptedRisk = contractRisk(record.contract)
      if (!acceptedRisk || !riskAllowsOperation(acceptedRisk, operation)) {
        throw kernelError("CONTRACT_RISK_EXCEEDED")
      }
    }
  }

  hasAcceptedContract(sessionID: string): boolean {
    const current = this.runtime.status(sessionID)
    const record = this.session(current.sessionID ?? sessionID)
    return !!record.contractHash && !!record.contract && !!record.runId && current.runId === record.runId
      && (record.preflight?.mutatingActionAllowed === true || record.preflight?.revalidationTrigger === "plan_basis_changed")
      && (!record.contractContext || record.contractContext.outcome === "accepted")
  }

  /** Kernel admission only; the Coordinator still enforces run, worker and verifier gates. */
  canVerifyRoot(sessionID: string) {
    return this.hasAcceptedContract(sessionID) && this.session(sessionID).state.planningState === "executing"
  }

  async recordExecutionResult(sessionID: string, runId: string, result: {
    output: string; changedFiles?: string[]; adapterId: string; modelId?: string
  }) {
    const record = this.session(sessionID)
    if (!record.runId || record.runId !== runId || this.runtime.status(sessionID).runId !== runId) {
      return this.status(sessionID)
    }
    if (!this.runtime.recordDomainResult) return this.status(sessionID)
    const status = await this.runtime.recordDomainResult({
      sessionID, runId,
      result: {
        output: result.output,
        changedFiles: [...(result.changedFiles ?? [])],
        adapterId: result.adapterId,
        ...(result.modelId ? { modelId: result.modelId } : {}),
      },
    })
    return this.emitStatus(sessionID, status)
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
    const domainPolicy = this.policyFor(record)
    const kernel: KernelStatus = {
      domain: record.state.domain,
      skills: record.state.skills,
      domainPolicy,
      domainBinding: record.domainBinding ? structuredClone(record.domainBinding) : undefined,
      domainPreparation: record.domainPreparation ? structuredClone(record.domainPreparation) : undefined,
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
      contractProcessing: record.contractContext ? (() => {
        const { candidate, originalRequest, ...processing } = record.contractContext
        return processing
      })() : undefined,
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
    return { ...status, ...preview, ...recovery, ...structuredClone(kernel), history }
  }

  private async review(sessionID: string, phase: MetaReviewPhase, original: unknown,
    revised?: (artifact: unknown) => void,
    assertCurrent = this.runGuard(sessionID, phase === "plan" ? "PLAN_RUN_CHANGED" : "CONTRACT_RUN_CHANGED"),
  ) {
    assertCurrent()
    if (!this.reviewer) {
      const error = kernelError("META_REVIEWER_UNAVAILABLE")
      await this.runtime.reportMetaReviewFailure?.(sessionID, error, phase, "harness")
      throw error
    }
    let artifact = structuredClone(original)
    let priorIssues: MetaReviewReport["issues"] = []
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      assertCurrent()
      let raw: unknown
      if (phase === "goal_contract") this.session(sessionID).state.planningState = "contract_reviewing"
      try {
        if (phase === "goal_contract" && this.session(sessionID).preflight) {
          this.session(sessionID).preflight!.reviewerCallCount += 1
        }
        raw = await this.reviewer({
          phase,
          sessionID,
          runId: this.session(sessionID).runId ?? "",
          artifact: structuredClone(artifact),
          priorIssues: structuredClone(priorIssues),
          attempt,
          context: this.session(sessionID).context,
          contractContext: phase === "goal_contract" ? structuredClone(this.session(sessionID).contractContext) : undefined,
          contractClarifications: phase === "goal_contract"
            ? (this.session(sessionID).contractHistory ?? [])
              .filter((item) => item.runId === this.session(sessionID).runId && item.answers.length > 0)
              .map(({ sessionID, runId, candidateRevision, contentHash, questions, answers }) =>
                structuredClone({ sessionID, runId, candidateRevision, contentHash, questions, answers }))
            : undefined,
        })
      } catch (error) {
        // Dispatch, transport and Host failures are not malformed model responses.
        assertCurrent()
        await this.runtime.reportMetaReviewFailure?.(sessionID, error, phase, "harness")
        throw error
      }
      assertCurrent()
      let report: MetaReviewReport
      try {
        report = parseMetaOutput(raw, phase)
        if (phase === "goal_contract") {
          const candidate = this.session(sessionID).contractContext!.candidate
          const ids = new Set([...candidate.body.claims.map((claim) => claim.claimId), ...candidate.body.criteria.map((criterion) => criterion.criterionId)])
          if (report.issues.some((issue) => issue.targetIds.some((id) => !ids.has(id)))) throw kernelError("META_REVIEW_TARGETS")
        }
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
      if (report.revisedArtifact !== undefined) {
        if (revised) {
          try { revised(report.revisedArtifact) }
          catch (error) {
            await this.runtime.reportMetaReviewFailure?.(sessionID, error, phase, "model")
            throw error
          }
        }
        artifact = structuredClone(report.revisedArtifact)
      }
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
    const demoFirst = this.policyFor(record).demoFirst
    const steps = units.map((unit: any, index: number) => ({
      id: String(unit.id),
      title: String(unit.title ?? unit.id),
      claimIds: stringArray(unit.claimIds),
      criterionIds: stringArray(unit.criterionIds),
      dependsOn: stringArray(unit.dependsOn),
      readSet: stringArray(unit.readSet),
      writeSet: stringArray(unit.writeSet),
      priority: demoFirst && index === 0 ? ("demo_required" as const) : ("required" as const),
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
    if (!planOnly && record.contractContext) record.contractContext.outcome = "revision_required"
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

function planningSignals(contract: any, graph: any, policy?: Pick<DomainPolicy, "requiresPlan">): PlanningSignals {
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
    domainRequiresPlan: policy?.requiresPlan,
  }
}

function verificationProfile(status: any): "fast" | "adaptive" | "strict" {
  const profile = status?.effectiveProfile ?? status?.configuredProfile
  return profile === "fast" || profile === "strict" ? profile : "adaptive"
}

interface NormalizedContractProposal {
  contract: ContractBody
  interpretation: InterpretationProposal
}

function preflightStatus(
  analysis: ContractValidateDedupeResult,
  reviewerCallCount = 0,
  reviewerAssumptions: string[] = [],
  result: ContractPreflightResult = analysis.result,
): ContractPreflightStatus {
  const interpretation = analysis.interpretation
  const requiredDecisions = (analysis.reviewDecision?.requiredDecisions ?? interpretation.candidates
    .filter((candidate) => candidate.impact !== "implementation_choice"))
    .map((candidate) => ({
      id: candidate.id,
      statement: candidate.statement,
      suggestedResolution: candidate.suggestedResolution,
      sourceRefs: candidate.sourceRefs,
      impact: candidate.impact,
      affectedClaimIds: candidate.affectedClaimIds,
      affectedCriterionIds: candidate.affectedCriterionIds,
    }))
  const assumptions = [
    ...(analysis.reviewDecision?.assumptions ?? interpretation.candidates
      .filter((candidate) => candidate.impact === "implementation_choice"))
      .map((candidate) => candidate.statement),
    ...reviewerAssumptions,
  ]
  return {
    ...result,
    pipelineStage: analysis.stage,
    scannedCandidateCount: analysis.scannedCandidateCount,
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
    executionSelection?: {
      adapterID?: string; modelID?: string; options?: Record<string, string>;
      capabilityRevision?: string; kind?: "model_api" | "agent_runtime";
      backendId?: string; connectionId?: string;
    };
  } } | undefined
  const model = value?.extra?.modelSelection
  const execution = value?.extra?.executionSelection
  if ((!model?.providerID || !model.modelID) && (!execution?.adapterID || !execution.modelID)) return
  if (!value?.messageID || !value.agent) return
  return {
    providerID: model?.providerID ?? `external/${execution!.adapterID}`,
    modelID: model?.modelID ?? execution!.modelID!,
    variant: value.extra?.variant,
    messageID: value.messageID,
    agent: value.agent,
    execution: execution?.adapterID && execution.modelID
      ? {
          adapterID: execution.adapterID,
          modelID: execution.modelID,
          options: execution.options,
          capabilityRevision: execution.capabilityRevision,
          kind: execution.kind,
          backendId: execution.backendId,
          connectionId: execution.connectionId,
        }
      : undefined,
  }
}

function contractRisk(contract: unknown): "low" | "medium" | "high" | "critical" | undefined {
  if (!contract || typeof contract !== "object") return undefined
  const criteria = (contract as { criteria?: unknown }).criteria
  if (!Array.isArray(criteria)) return undefined
  const order = { low: 0, medium: 1, high: 2, critical: 3 } as const
  let result: keyof typeof order | undefined
  for (const value of criteria) {
    if (!value || typeof value !== "object" || (value as { required?: unknown }).required === false) continue
    const risk = (value as { risk?: unknown }).risk
    if (typeof risk !== "string" || !(risk in order)) continue
    const candidate = risk as keyof typeof order
    if (!result || order[candidate] > order[result]) result = candidate
  }
  return result
}

function planDomainBinding(binding: DomainExecutionBinding, preparation: DomainPreparation): PlanDomainBinding {
  return {
    schemaVersion: "plan-domain-binding-v1",
    selection: structuredClone(binding.selection),
    policy: structuredClone(binding.policy),
    module: { ...binding.module },
    preparationStrategy: { ...binding.preparationStrategy },
    proposalStrategy: { ...binding.proposalStrategy },
    overlays: structuredClone(binding.overlays),
    skills: structuredClone(preparation.skills ?? []),
  }
}

function normalizeDomainExecutor(explicit: unknown, legacy: unknown, context: unknown): DomainExecutorSelection {
  const selected = explicit && typeof explicit === "object" ? explicit as Record<string, unknown> : undefined
  const execution = legacy && typeof legacy === "object" ? legacy as Record<string, unknown> : undefined
  const source = context && typeof context === "object" ? context as { extra?: {
    modelSelection?: { providerID?: unknown; modelID?: unknown }
  } } : undefined
  const model = source?.extra?.modelSelection
  const id = selected?.id ?? execution?.adapterID ?? execution?.backendId ?? "session-model"
  const revision = selected?.revision ?? execution?.capabilityRevision ?? "1"
  const kind = selected?.kind ?? execution?.kind ?? "model_api"
  const providerId = selected?.providerId ?? model?.providerID
  const modelId = selected?.modelId ?? execution?.modelID ?? execution?.modelId ?? model?.modelID
  const connectionId = selected?.connectionId ?? execution?.connectionId
  const rawOptions = selected?.options ?? execution?.options ?? execution?.nativeOptions
  const options = rawOptions && typeof rawOptions === "object"
    ? Object.fromEntries(Object.entries(rawOptions).filter((entry): entry is [string, string] => typeof entry[1] === "string"))
    : {}
  if (typeof id !== "string" || !id.trim() || typeof revision !== "string" || !revision.trim()
      || (kind !== "model_api" && kind !== "agent_runtime")
      || (connectionId !== undefined && typeof connectionId !== "string")
      || (providerId !== undefined && typeof providerId !== "string")
      || (modelId !== undefined && typeof modelId !== "string")) {
    throw kernelError("DOMAIN_EXECUTOR_INVALID")
  }
  return {
    id: id.trim(), revision: revision.trim(), kind,
    ...(connectionId ? { connectionId } : {}),
    ...(providerId ? { providerId } : {}), ...(modelId ? { modelId } : {}), options,
  }
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
