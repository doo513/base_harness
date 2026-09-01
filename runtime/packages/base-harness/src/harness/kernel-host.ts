import {
  allowsOperation,
  applyControl,
  createKernelSessionState,
  decidePlanning,
  operationForTool,
  parseMetaReview,
  validatePlanSpec,
  validatePlanCoverage,
  type HarnessControl,
  type KernelSessionState,
  type MetaReviewPhase,
  type MetaReviewReport,
  type PlanSpec,
  type PlanningDecision,
  type PlanningSignals,
} from "@base-harness/kernel"
import { createHash, randomUUID } from "node:crypto"
import { mkdir, readFile, rename, stat, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"

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
  planningPreference: KernelSessionState["planningPreference"]
  planningState: KernelSessionState["planningState"]
  planningDecision?: PlanningDecision
  activePlanId?: string
  activePlanRevision?: number
  metaReview?: {
    phase: MetaReviewPhase
    outcome: MetaReviewReport["outcome"]
    issueCount: number
    blockingIssueCount: number
    issues: MetaReviewReport["issues"]
  }
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
  revisionOnly?: boolean
  explicitSelection?: boolean
}

interface RuntimeCoordinator {
  openRun(input: any): Promise<any>
  proposeContract(sessionID: string, proposal: any): Promise<any>
  acceptWorkGraph(sessionID: string, graph: any, context?: unknown): Promise<any>
  status(sessionID: string): any
}

export class KernelHost {
  private readonly sessions = new Map<string, SessionRecord>()
  private reviewer?: (request: MetaReviewRequest) => Promise<unknown>

  constructor(private readonly runtime: RuntimeCoordinator) {}

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

  async openRun(input: any) {
    const record = this.session(input.sessionID)
    if (!record.runId && !record.explicitSelection && input.defaultDomain) {
      record.state = applyControl(record.state, {
        type: "domain.set",
        domain: input.defaultDomain,
      })
    }
    if (record.state.planningState === "plan_ready") {
      record.revisionOnly = true
      record.state = { ...record.state, planningState: "plan_building" }
    } else {
      record.state = { ...record.state, planningState: "contract_building" }
    }
    record.workspace = input.workspace
    record.goal = input.goal
    record.context = input.context
    const result = await this.runtime.openRun(input)
    record.runId = result.runId
    return this.mergeStatus(input.sessionID, result)
  }

  async proposeContract(sessionID: string, proposal: unknown, context?: unknown) {
    const record = this.session(sessionID)
    if (context) record.context = context
    record.state = { ...record.state, planningState: "contract_reviewing" }
    const reviewed = await this.review(sessionID, "goal_contract", proposal)
    if (reviewed.report.outcome === "needs_input") {
      record.state = { ...record.state, planningState: "awaiting_input" }
      return this.mergeStatus(sessionID, this.runtime.status(sessionID))
    }
    if (reviewed.report.outcome === "revise" && reviewed.artifact === proposal) {
      record.state = { ...record.state, planningState: "awaiting_input" }
      return this.mergeStatus(sessionID, this.runtime.status(sessionID))
    }
    assertContractProposal(reviewed.artifact)
    record.contract = reviewed.artifact
    record.contractRevision += 1
    record.contractHash = digest(reviewed.artifact)
    const result = await this.runtime.proposeContract(sessionID, reviewed.artifact)
    record.state = { ...record.state, planningState: "planning_decision" }
    return this.mergeStatus(sessionID, result)
  }

  async acceptWorkGraph(sessionID: string, graph: any, context?: unknown) {
    const record = this.session(sessionID)
    if (context) record.context = context
    record.graphContext = context
    if (!record.contract || !record.contractHash || !record.workspace || !record.runId) {
      throw kernelError("CONTRACT_REQUIRED")
    }
    const executionGraph = record.state.skills.includes("hackathon")
      ? prioritizeDemoGraph(graph)
      : graph
    const decision = record.revisionOnly
      ? "planned"
      : decidePlanning(record.state, planningSignals(record.contract, executionGraph))
    record.decision = decision
    if (decision === "direct" && record.state.planningPreference !== "plan_once") {
      record.state = { ...record.state, planningState: "executing" }
      return this.mergeStatus(
        sessionID,
        await this.runtime.acceptWorkGraph(sessionID, executionGraph, context),
      )
    }

    record.state = { ...record.state, planningState: "plan_building" }
    const plan = await this.buildPlan(record, executionGraph)
    record.state = { ...record.state, planningState: "plan_reviewing" }
    const reviewed = await this.review(sessionID, "plan", plan)
    if (reviewed.report.outcome !== "pass") {
      record.state = { ...record.state, planningState: "awaiting_input" }
      return this.mergeStatus(sessionID, this.runtime.status(sessionID))
    }
    const canonical = reviewed.artifact as PlanSpec
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
    await savePlan(canonical)
    record.graph = executionGraph
    record.plan = canonical
    record.graphContext = withPlanContext(context, canonical)
    const planOnly = record.state.planningPreference === "plan_once" || record.revisionOnly === true
    record.revisionOnly = false
    record.state = {
      ...record.state,
      planningPreference: "auto",
      planningState: planOnly ? "plan_ready" : "executing",
      activePlanId: canonical.planId,
      activePlanRevision: canonical.revision,
    }
    if (planOnly) return this.mergeStatus(sessionID, this.runtime.status(sessionID))
    return this.mergeStatus(
      sessionID,
      await this.runtime.acceptWorkGraph(sessionID, executionGraph, record.graphContext),
    )
  }

  async control(sessionID: string, control: HarnessControl) {
    const record = this.session(sessionID)
    const active =
      record.state.planningState !== "idle" &&
      record.state.planningState !== "plan_ready" &&
      record.state.planningState !== "awaiting_input"
    if (active) throw kernelError("RUN_ACTIVE")
    if (control.type === "domain.set" || control.type === "skill.set") {
      record.explicitSelection = true
    }
    if (control.type === "planning.execute") {
      if (record.state.planningState !== "plan_ready" || !record.plan || !record.graph) {
        throw kernelError("PLAN_NOT_READY")
      }
      if (control.planId && control.planId !== record.plan.planId) throw kernelError("PLAN_ID_MISMATCH")
      await assertPlanFresh(record.plan, record.workspace!)
      if (
        record.plan.domain !== record.state.domain ||
        digest(record.plan.skills) !== digest(record.state.skills) ||
        record.plan.goalContractHash !== record.contractHash
      ) {
        throw kernelError("PLAN_STALE")
      }
      record.state = { ...record.state, planningState: "executing" }
      await this.runtime.acceptWorkGraph(sessionID, record.graph, record.graphContext)
      return this.status(sessionID)
    }
    if (control.type === "planning.discard") {
      if (record.state.planningState !== "plan_ready" && record.state.planningState !== "awaiting_input") {
        throw kernelError("PLAN_NOT_DISCARDABLE")
      }
      record.plan = undefined
      record.graph = undefined
    }
    record.state = applyControl(record.state, control)
    return this.status(sessionID)
  }

  assertToolAllowed(sessionID: string, toolID: string, subagentType?: string) {
    const record = this.session(sessionID)
    const operation = operationForTool(toolID)
    if (record.state.domain === "general" && operation === "unknown") {
      throw kernelError("DOMAIN_PERMISSION_UNKNOWN")
    }
    if (!allowsOperation(record.state, operation, subagentType)) {
      throw kernelError(
        record.state.domain === "general" ? "DOMAIN_PERMISSION_DENIED" : "PLAN_ONLY_MUTATION_DENIED",
      )
    }
  }

  status(sessionID: string) {
    return this.mergeStatus(sessionID, this.runtime.status(sessionID))
  }

  private mergeStatus(sessionID: string, status: any) {
    const record = this.session(sessionID)
    const kernel: KernelStatus = {
      domain: record.state.domain,
      skills: record.state.skills,
      planningPreference: record.state.planningPreference,
      planningState: record.state.planningState,
      planningDecision: record.decision,
      activePlanId: record.state.activePlanId,
      activePlanRevision: record.state.activePlanRevision,
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
    return { ...status, ...kernel }
  }

  private async review(sessionID: string, phase: MetaReviewPhase, original: unknown) {
    if (!this.reviewer) throw kernelError("META_REVIEWER_UNAVAILABLE")
    let artifact = original
    let priorIssues: MetaReviewReport["issues"] = []
    for (let attempt = 1; attempt <= 2; attempt += 1) {
      let raw: unknown
      try {
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
        if (attempt === 2) throw kernelError("META_REVIEW_MODEL_PROTOCOL", error)
        continue
      }
      let report: MetaReviewReport
      try {
        report = parseMetaOutput(raw, phase)
      } catch (error) {
        if (attempt === 2) throw kernelError("META_REVIEW_MODEL_PROTOCOL", error)
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
        record.review?.issues
          .filter((issue) => issue.severity === "warning")
          .map((issue) => issue.statement) ?? [],
    }
    validatePlanSpec(plan)
    validatePlanCoverage(plan, requiredIDs(record.contract, "claims", "claimId"), requiredIDs(record.contract, "criteria", "criterionId"))
    return plan
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
  const targets = new Set(units.flatMap((unit: any) => stringArray(unit.writeSet)))
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
      (claim: any) => claim.external === true || claim.scope?.external === true,
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
            1,
        ),
      ),
    ),
  }
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

async function savePlan(plan: PlanSpec) {
  const stateRoot =
    process.platform === "win32"
      ? path.join(process.env.LOCALAPPDATA ?? path.join(os.homedir(), "AppData", "Local"), "base-harness")
      : path.join(
          process.env.XDG_STATE_HOME ?? path.join(os.homedir(), ".local", "state"),
          "base-harness",
        )
  const directory = path.join(stateRoot, "plans", plan.planId)
  await mkdir(directory, { recursive: true })
  const target = path.join(directory, String(plan.revision) + ".json")
  const temporary = [target, process.pid, randomUUID(), "tmp"].join(".")
  await writeFile(temporary, JSON.stringify(plan, null, 2), { encoding: "utf8", mode: 0o600 })
  await rename(temporary, target)
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
