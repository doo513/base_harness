import type { MetaReviewPhase, MetaReviewOutcome, MetaIssueKind, MetaReviewIssue, MetaReviewReport, UncertaintyKind, DecisionImpact, UncertaintyCandidate, InterpretationProposal, PreflightReason, ContractPreflightResult, ContractRevalidationTrigger, ContractPreflightSignals, ContractPipelineStage, ContractPrepareResult, ContractScanBindings, ContractScanResult, ContractValidateDedupeResult, CandidateSourceReference as SourceReference } from "@base-harness/domain-contracts"
import type { DomainId, SkillId, DomainOperation, DomainSelection, DomainSelectionControl, ReadonlyValue, Risk } from "@base-harness/domain-contracts"
export type { DomainId, SkillId } from "@base-harness/domain-contracts"
export * from "./autonomous/schema"
export * from "./autonomous/admission"
export type PlanningPreference = "auto" | "plan_once"
export type PlanningDecision = "direct" | "planned"

export interface ExecutionSelection {
  adapterID: string
  modelID?: string
  options?: Record<string, string>
  capabilityRevision?: string
  kind?: "model_api" | "agent_runtime"
  backendId?: string
  connectionId?: string
}
export type PlanningState =
  | "idle"
  | "contract_building"
  | "contract_preparing"
  | "contract_scanning"
  | "contract_validate_dedupe"
  // Retained for restored status compatibility; new runs use the three states above.
  | "contract_preflight"
  | "contract_reviewing"
  | "awaiting_input"
  | "planning_decision"
  | "plan_building"
  | "plan_reviewing"
  | "plan_ready"
  | "executing"

export interface KernelSessionState {
  domain: DomainId
  skills: SkillId[]
  planningPreference: PlanningPreference
  planningState: PlanningState
  execution?: ExecutionSelection
  activePlanId?: string
  activePlanRevision?: number
}

export interface PlanBasis {
  path: string
  sha256: string
}

export interface PlanStep {
  id: string
  title: string
  claimIds: string[]
  criterionIds: string[]
  dependsOn: string[]
  readSet: string[]
  writeSet: string[]
  priority: "demo_required" | "required" | "optional"
}

export interface PlanSpec {
  schemaVersion: "plan-v1"
  planId: string
  revision: number
  runId: string
  domain: DomainId
  skills: SkillId[]
  goalContractId: string
  goalContractRevision: number
  goalContractHash: string
  basis: PlanBasis[]
  steps: PlanStep[]
  workGraph?: unknown
  assumptions: string[]
}

export type { MetaReviewPhase, MetaReviewOutcome, MetaIssueKind, MetaReviewIssue, MetaReviewReport, UncertaintyKind, DecisionImpact, UncertaintyCandidate, InterpretationProposal, PreflightReason, ContractPreflightResult, ContractRevalidationTrigger, ContractPreflightSignals, ContractPipelineStage, ContractPrepareResult, ContractScanBindings, ContractScanResult, ContractValidateDedupeResult, CandidateSourceReference as SourceReference } from "@base-harness/domain-contracts"
export interface PlanningSignals {
  risk: "low" | "medium" | "high" | "critical"
  requiredClaimCount: number
  requiredCriterionCount: number
  targetCount: number
  hasExternalClaim: boolean
  applicabilityResolved: boolean
  requiredEvidenceFamilyCount: number
  /** Supplied by the selected DomainProfile; Kernel does not know domain names. */
  domainRequiresPlan?: boolean
}

export interface DomainPolicyInput {
  /** Operation names are intentionally opaque to Kernel domain implementations. */
  allowedOperations?: readonly ToolOperation[]
  /** Domain-owned allowlist for delegated agent roles. */
  allowedSubagentTypes?: readonly string[]
  requiresPlan?: boolean
}

export type HarnessControl =
  | DomainSelectionControl
  | { type: "execution.select"; selection?: ExecutionSelection }
  | { type: "planning.plan_once" }
  | { type: "planning.discard" }
  | { type: "planning.execute"; planId?: string }

export type ToolOperation = DomainOperation | "unknown"

const riskRank: Readonly<Record<Risk, number>> = {
  low: 0,
  medium: 1,
  high: 2,
  critical: 3,
}

/** Minimum contract risk required by an operation, independent of actor arguments. */
export function minimumRiskForOperation(operation: ToolOperation): Risk {
  if (operation === "execute") return "high"
  if (operation === "delegate") return "medium"
  if (operation === "unknown") return "critical"
  return "low"
}

export function riskAllowsOperation(contractRisk: Risk, operation: ToolOperation): boolean {
  return riskRank[contractRisk] >= riskRank[minimumRiskForOperation(operation)]
}

const metaPhases = new Set<MetaReviewPhase>(["goal_contract", "plan"])
const metaOutcomes = new Set<MetaReviewOutcome>(["pass", "revise", "needs_input"])
const issueKinds = new Set<MetaIssueKind>([
  "omission",
  "contradiction",
  "ambiguity",
  "scope",
  "applicability",
  "coverage",
  "verifier_mismatch",
  "unsafe_assumption",
])
export function createKernelSessionState(selection: ReadonlyValue<DomainSelection> = { domain: "develop", skills: [] }): KernelSessionState {
  return {
    domain: selection.domain,
    skills: [...selection.skills],
    planningPreference: "auto",
    planningState: "idle",
  }
}

export function applyControl(state: KernelSessionState, control: HarnessControl): KernelSessionState {
  if (control.type === "domain.set") {
    return {
      ...state,
      domain: control.domain,
    }
  }
  if (control.type === "skill.set") {
    const skills = new Set(state.skills)
    if (control.enabled) skills.add(control.skill)
    else skills.delete(control.skill)
    return {
      ...state,
      skills: [...skills],
    }
  }

  if (control.type === "execution.select") {
    return {
      ...state,
      execution: control.selection
        ? {
            ...control.selection,
            options: control.selection.options ? { ...control.selection.options } : undefined,
            kind: control.selection.kind ?? "agent_runtime",
          }
        : undefined,
    }
  }
  if (control.type === "planning.plan_once") {
    return { ...state, planningPreference: "plan_once" }
  }
  if (control.type === "planning.discard") {
    return {
      ...state,
      planningPreference: "auto",
      planningState: "idle",
      activePlanId: undefined,
      activePlanRevision: undefined,
    }
  }
  return state
}

export function decidePlanning(
  state: KernelSessionState,
  signals: PlanningSignals,
): PlanningDecision {
  if (state.planningPreference === "plan_once") return "planned"
  if (signals.domainRequiresPlan) return "planned"
  if (signals.risk === "high" || signals.risk === "critical") return "planned"
  if (signals.requiredClaimCount > 1 || signals.requiredCriterionCount > 1) return "planned"
  if (signals.targetCount > 1 || signals.hasExternalClaim) return "planned"
  if (!signals.applicabilityResolved || signals.requiredEvidenceFamilyCount > 1) return "planned"
  return "direct"
}

export { parseInterpretationProposal, validateInterpretationBindings } from "./contract/interpretation"
export { prepareContractPreflight, prepareContract } from "./contract/prepare"
export { scanContractPreflight, scanContract } from "./contract/scan"
export { validateAndDedupeContractPreflight, validateContract, assertContractProposal, dedupeContractDiagnostics } from "./contract/validate"
export { decideContractPreflight } from "./contract/preflight"
export type { PreparedContract, ScannedContract, ContractStructureResult, ContractDiagnostic } from "./contract/types"

export function operationForTool(toolID: string): ToolOperation {
  const operations: Record<string, ToolOperation> = {
    read: "read",
    glob: "read",
    grep: "search",
    list: "read",
    lsp: "read",
    skill: "read",
    todowrite: "control",
    invalid: "control",
    webfetch: "search",
    websearch: "search",
    codesearch: "search",
    question: "question",
    harness_contract: "control",
    harness_workgraph: "control",
    harness_evidence: "control",
    harness_ready: "control",
    task: "delegate",
    write: "mutate",
    edit: "mutate",
    apply_patch: "mutate",
    bash: "execute",
    shell: "execute",
    argv: "execute",
  }
  return operations[toolID] ?? "unknown"
}

export function allowsOperation(
  state: KernelSessionState,
  operation: ToolOperation,
  subagentType?: string,
  domainPolicy?: DomainPolicyInput,
): boolean {
  if (
    state.planningState === "contract_building" ||
    state.planningState === "contract_preparing" ||
    state.planningState === "contract_scanning" ||
    state.planningState === "contract_validate_dedupe" ||
    state.planningState === "contract_preflight" ||
    state.planningState === "contract_reviewing" ||
    state.planningState === "planning_decision" ||
    state.planningState === "plan_building" ||
    state.planningState === "plan_reviewing" ||
    state.planningState === "plan_ready" ||
    state.planningState === "awaiting_input"
  ) {
    if (operation === "delegate") return subagentType === "explore" || subagentType === "meta-review"
    return operation === "read" || operation === "search" || operation === "question" || operation === "control"
  }
  if (domainPolicy?.allowedOperations && !domainPolicy.allowedOperations.includes(operation)) return false
  if (
    operation === "delegate" &&
    domainPolicy?.allowedSubagentTypes &&
    (!subagentType || !domainPolicy.allowedSubagentTypes.includes(subagentType))
  ) return false
  void subagentType
  return true
}

export function parseMetaReview(value: unknown, expectedPhase: MetaReviewPhase): MetaReviewReport {
  if (!value || typeof value !== "object") throw new Error("META_REVIEW_SCHEMA")
  const record = value as Record<string, unknown>
  if (!metaPhases.has(record.phase as MetaReviewPhase) || record.phase !== expectedPhase) {
    throw new Error("META_REVIEW_PHASE")
  }
  if (!metaOutcomes.has(record.outcome as MetaReviewOutcome)) throw new Error("META_REVIEW_OUTCOME")
  if (!Array.isArray(record.issues)) throw new Error("META_REVIEW_ISSUES")
  const issueIDs = new Set<string>()
  const issues = record.issues.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("META_REVIEW_ISSUE")
    const issue = raw as Record<string, unknown>
    if (typeof issue.id !== "string" || !issue.id.trim() || issueIDs.has(issue.id) || !issueKinds.has(issue.kind as MetaIssueKind)) {
      throw new Error("META_REVIEW_ISSUE_ID")
    }
    issueIDs.add(issue.id as string)
    if (issue.severity !== "blocking" && issue.severity !== "warning") {
      throw new Error("META_REVIEW_SEVERITY")
    }
    if (!Array.isArray(issue.targetIds) || !issue.targetIds.every((item) => typeof item === "string")) {
      throw new Error("META_REVIEW_TARGETS")
    }
    if (!Array.isArray(issue.sourceRefs)) throw new Error("META_REVIEW_SOURCES")
    const sourceRefs = issue.sourceRefs.map((rawSource) => {
      if (!rawSource || typeof rawSource !== "object") throw new Error("META_REVIEW_SOURCE")
      const source = rawSource as Record<string, unknown>
      if (typeof source.source !== "string") throw new Error("META_REVIEW_SOURCE_ID")
      return {
        source: source.source,
        pointer: typeof source.pointer === "string" ? source.pointer : undefined,
        quote: typeof source.quote === "string" ? source.quote : undefined,
      } satisfies SourceReference
    })
    if (typeof issue.statement !== "string" || !issue.statement.trim()) throw new Error("META_REVIEW_STATEMENT")
    return {
      id: issue.id,
      kind: issue.kind as MetaIssueKind,
      severity: issue.severity,
      targetIds: issue.targetIds as string[],
      sourceRefs,
      statement: issue.statement,
      suggestedResolution:
        typeof issue.suggestedResolution === "string" ? issue.suggestedResolution : undefined,
    } satisfies MetaReviewIssue
  })
  const blocking = issues.some((issue) => issue.severity === "blocking")
  if (record.outcome === "pass" && blocking) throw new Error("META_REVIEW_BLOCKING_PASS")
  if ((record.outcome === "revise" || record.outcome === "needs_input") && !blocking) {
    throw new Error("META_REVIEW_NONBLOCKING_STOP")
  }
  return {
    phase: expectedPhase,
    outcome: record.outcome as MetaReviewOutcome,
    issues,
    revisedArtifact: record.revisedArtifact,
  }
}

export function validatePlanSpec(plan: PlanSpec): void {
  if (plan.schemaVersion !== "plan-v1" || !plan.planId || plan.revision < 1) throw new Error("PLAN_SCHEMA")
  const ids = new Set(plan.steps.map((step) => step.id))
  if (ids.size !== plan.steps.length) throw new Error("PLAN_DUPLICATE_STEP")
  for (const step of plan.steps) {
    if (!step.claimIds.length || !step.criterionIds.length) throw new Error("PLAN_COVERAGE")
    if (step.dependsOn.some((id) => !ids.has(id) || id === step.id)) throw new Error("PLAN_DEPENDENCY")
  }
  const visiting = new Set<string>()
  const visited = new Set<string>()
  const byID = new Map(plan.steps.map((step) => [step.id, step]))
  const visit = (id: string) => {
    if (visiting.has(id)) throw new Error("PLAN_CYCLE")
    if (visited.has(id)) return
    visiting.add(id)
    for (const dependency of byID.get(id)?.dependsOn ?? []) visit(dependency)
    visiting.delete(id)
    visited.add(id)
  }
  for (const id of ids) visit(id)
}

export function validatePlanCoverage(
  plan: PlanSpec,
  requiredClaimIds: string[],
  requiredCriterionIds: string[],
): void {
  const claims = new Set(plan.steps.flatMap((step) => step.claimIds))
  const criteria = new Set(plan.steps.flatMap((step) => step.criterionIds))
  if (requiredClaimIds.some((id) => !claims.has(id))) throw new Error("PLAN_CLAIM_COVERAGE")
  if (requiredCriterionIds.some((id) => !criteria.has(id))) throw new Error("PLAN_CRITERION_COVERAGE")
}

export { defaultContractReviewPolicy, reviewContractFacts } from "./contract/review-policy"
export type { ContractReviewPolicy, ContractReviewFacts, ContractReviewDecision } from "@base-harness/domain-contracts"
