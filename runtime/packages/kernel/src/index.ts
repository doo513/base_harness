export type DomainId = "develop" | "general"
export type SkillId = "hackathon"
export type PlanningPreference = "auto" | "plan_once"
export type PlanningDecision = "direct" | "planned"
export type PlanningState =
  | "idle"
  | "contract_building"
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

export type MetaReviewPhase = "goal_contract" | "plan"
export type MetaReviewOutcome = "pass" | "revise" | "needs_input"
export type MetaIssueKind =
  | "omission"
  | "contradiction"
  | "ambiguity"
  | "scope"
  | "applicability"
  | "coverage"
  | "verifier_mismatch"
  | "unsafe_assumption"

export interface SourceReference {
  source: string
  pointer?: string
  quote?: string
}

export interface MetaReviewIssue {
  id: string
  kind: MetaIssueKind
  severity: "blocking" | "warning"
  targetIds: string[]
  sourceRefs: SourceReference[]
  statement: string
  suggestedResolution?: string
}

export interface MetaReviewReport {
  phase: MetaReviewPhase
  outcome: MetaReviewOutcome
  issues: MetaReviewIssue[]
  revisedArtifact?: unknown
}

export type UncertaintyKind =
  | "multiple_interpretations"
  | "missing_decision"
  | "assumption"
  | "conflict"

export type DecisionImpact =
  | "implementation_choice"
  | "user_preference"
  | "required_criterion"
  | "scope"
  | "security"
  | "external_effect"
  | "verifier_applicability"

export interface UncertaintyCandidate {
  id: string
  kind: UncertaintyKind
  impact: DecisionImpact
  affectedClaimIds: string[]
  affectedCriterionIds: string[]
  sourceRefs: SourceReference[]
  statement: string
  suggestedResolution?: string
}

export interface InterpretationProposal {
  version: 1
  candidates: UncertaintyCandidate[]
}

export type PreflightReason =
  | "multiple_valid_interpretations"
  | "missing_required_value"
  | "unsafe_default"
  | "scope_conflict"
  | "applicability_gap"
  | "criterion_not_observable"
  | "verifier_mismatch"
  | "external_side_effect"
  | "high_risk"
  | "strict_profile"
  | "complex_contract"

export interface ContractPreflightResult {
  version: 1
  decision: "accept" | "meta_review_required" | "needs_input"
  reasons: PreflightReason[]
  affectedClaimIds: string[]
  affectedCriterionIds: string[]
  mutatingActionAllowed: boolean
}

export type ContractRevalidationTrigger =
  | "new_required_dependency"
  | "scope_expansion_requested"
  | "applicability_changed"
  | "plan_basis_changed"
  | "verifier_became_unavailable"
  | "required_criterion_changed"

export interface ContractPreflightSignals {
  risk: "low" | "medium" | "high" | "critical"
  configuredProfile: "fast" | "adaptive" | "strict"
  requiredClaimCount: number
  requiredCriterionCount: number
  hasExternalClaim: boolean
  applicabilityResolved: boolean
}

export interface PlanningSignals {
  risk: "low" | "medium" | "high" | "critical"
  requiredClaimCount: number
  requiredCriterionCount: number
  targetCount: number
  hasExternalClaim: boolean
  applicabilityResolved: boolean
  requiredEvidenceFamilyCount: number
}

export type HarnessControl =
  | { type: "domain.set"; domain: DomainId }
  | { type: "skill.set"; skill: SkillId; enabled: boolean }
  | { type: "planning.plan_once" }
  | { type: "planning.discard" }
  | { type: "planning.execute"; planId?: string }

export type ToolOperation = "read" | "search" | "question" | "control" | "mutate" | "execute" | "delegate" | "unknown"

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
const uncertaintyKinds = new Set<UncertaintyKind>([
  "multiple_interpretations",
  "missing_decision",
  "assumption",
  "conflict",
])
const decisionImpacts = new Set<DecisionImpact>([
  "implementation_choice",
  "user_preference",
  "required_criterion",
  "scope",
  "security",
  "external_effect",
  "verifier_applicability",
])

export function createKernelSessionState(): KernelSessionState {
  return {
    domain: "develop",
    skills: [],
    planningPreference: "auto",
    planningState: "idle",
  }
}

export function applyControl(state: KernelSessionState, control: HarnessControl): KernelSessionState {
  if (control.type === "domain.set") {
    return {
      ...state,
      domain: control.domain,
      skills: [],
    }
  }
  if (control.type === "skill.set") {
    const skills = new Set(state.skills)
    if (control.enabled) skills.add(control.skill)
    else skills.delete(control.skill)
    return {
      ...state,
      domain: control.enabled ? "develop" : state.domain,
      skills: [...skills],
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
  if (state.skills.includes("hackathon")) return "planned"
  if (signals.risk === "high" || signals.risk === "critical") return "planned"
  if (signals.requiredClaimCount > 1 || signals.requiredCriterionCount > 1) return "planned"
  if (signals.targetCount > 1 || signals.hasExternalClaim) return "planned"
  if (!signals.applicabilityResolved || signals.requiredEvidenceFamilyCount > 1) return "planned"
  return "direct"
}

export function parseInterpretationProposal(value: unknown): InterpretationProposal {
  if (!value || typeof value !== "object") throw new Error("INTERPRETATION_SCHEMA")
  const input = value as Record<string, unknown>
  if (input.version !== 1 || !Array.isArray(input.candidates)) {
    throw new Error("INTERPRETATION_SCHEMA")
  }
  const ids = new Set<string>()
  const candidates = input.candidates.map((raw, index): UncertaintyCandidate => {
    if (!raw || typeof raw !== "object") throw new Error("INTERPRETATION_CANDIDATE")
    const candidate = raw as Record<string, unknown>
    const id = requiredInterpretationString(candidate.id, `candidate[${index}].id`)
    if (ids.has(id)) throw new Error("INTERPRETATION_DUPLICATE_ID")
    ids.add(id)
    if (!uncertaintyKinds.has(candidate.kind as UncertaintyKind)) {
      throw new Error("INTERPRETATION_KIND")
    }
    if (!decisionImpacts.has(candidate.impact as DecisionImpact)) {
      throw new Error("INTERPRETATION_IMPACT")
    }
    if (!Array.isArray(candidate.sourceRefs) || candidate.sourceRefs.length === 0) {
      throw new Error("INTERPRETATION_SOURCE")
    }
    const sourceRefs = candidate.sourceRefs.map((rawSource): SourceReference => {
      if (!rawSource || typeof rawSource !== "object") throw new Error("INTERPRETATION_SOURCE")
      const source = rawSource as Record<string, unknown>
      return {
        source: requiredInterpretationString(source.source, "sourceRefs.source"),
        pointer: optionalInterpretationString(source.pointer),
        quote: optionalInterpretationString(source.quote),
      }
    })
    return {
      id,
      kind: candidate.kind as UncertaintyKind,
      impact: candidate.impact as DecisionImpact,
      affectedClaimIds: interpretationStringArray(candidate.affectedClaimIds),
      affectedCriterionIds: interpretationStringArray(candidate.affectedCriterionIds),
      sourceRefs,
      statement: requiredInterpretationString(candidate.statement, `candidate[${index}].statement`),
      suggestedResolution: optionalInterpretationString(candidate.suggestedResolution),
    }
  })
  return { version: 1, candidates }
}

export function validateInterpretationBindings(
  proposal: InterpretationProposal,
  claimIds: readonly string[],
  criterionIds: readonly string[],
): void {
  const claims = new Set(claimIds)
  const criteria = new Set(criterionIds)
  for (const candidate of proposal.candidates) {
    if (!candidate.affectedClaimIds.length && !candidate.affectedCriterionIds.length) {
      throw new Error("INTERPRETATION_UNBOUND")
    }
    if (candidate.affectedClaimIds.some((id) => !claims.has(id))) {
      throw new Error("INTERPRETATION_UNKNOWN_CLAIM")
    }
    if (candidate.affectedCriterionIds.some((id) => !criteria.has(id))) {
      throw new Error("INTERPRETATION_UNKNOWN_CRITERION")
    }
  }
}

export function decideContractPreflight(
  proposal: InterpretationProposal,
  signals: ContractPreflightSignals,
): ContractPreflightResult {
  const consequential = proposal.candidates.filter(
    (candidate) => candidate.impact !== "implementation_choice",
  )
  if (consequential.length) {
    return {
      version: 1,
      decision: "needs_input",
      reasons: uniquePreflightReasons(consequential.map(reasonForCandidate)),
      affectedClaimIds: [...new Set(consequential.flatMap((candidate) => candidate.affectedClaimIds))],
      affectedCriterionIds: [
        ...new Set(consequential.flatMap((candidate) => candidate.affectedCriterionIds)),
      ],
      mutatingActionAllowed: false,
    }
  }

  const reasons: PreflightReason[] = []
  if (signals.risk === "high" || signals.risk === "critical") reasons.push("high_risk")
  if (signals.configuredProfile === "strict") reasons.push("strict_profile")
  if (signals.hasExternalClaim) reasons.push("external_side_effect")
  if (!signals.applicabilityResolved) reasons.push("applicability_gap")
  if (signals.requiredClaimCount > 1 || signals.requiredCriterionCount > 1) {
    reasons.push("complex_contract")
  }
  if (reasons.length) {
    return {
      version: 1,
      decision: "meta_review_required",
      reasons: uniquePreflightReasons(reasons),
      affectedClaimIds: [],
      affectedCriterionIds: [],
      mutatingActionAllowed: false,
    }
  }
  return {
    version: 1,
    decision: "accept",
    reasons: [],
    affectedClaimIds: [],
    affectedCriterionIds: [],
    mutatingActionAllowed: true,
  }
}

function reasonForCandidate(candidate: UncertaintyCandidate): PreflightReason {
  if (candidate.impact === "scope") return "scope_conflict"
  if (candidate.impact === "verifier_applicability") return "verifier_mismatch"
  if (candidate.impact === "external_effect") return "external_side_effect"
  if (candidate.kind === "multiple_interpretations") return "multiple_valid_interpretations"
  if (candidate.kind === "missing_decision") return "missing_required_value"
  return "unsafe_default"
}

function requiredInterpretationString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`INTERPRETATION_STRING:${field}`)
  return value
}

function optionalInterpretationString(value: unknown): string | undefined {
  return value === undefined ? undefined : requiredInterpretationString(value, "optional")
}

function interpretationStringArray(value: unknown): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string" && item.length > 0)) {
    throw new Error("INTERPRETATION_ID_LIST")
  }
  return value
}

function uniquePreflightReasons(reasons: PreflightReason[]): PreflightReason[] {
  return [...new Set(reasons)]
}

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
): boolean {
  if (
    state.planningState === "contract_building" ||
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
  if (state.domain === "general") {
    if (operation === "delegate") return subagentType === "explore" || subagentType === "meta-review"
    return operation === "read" || operation === "search" || operation === "question" || operation === "control"
  }
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
  const issues = record.issues.map((raw) => {
    if (!raw || typeof raw !== "object") throw new Error("META_REVIEW_ISSUE")
    const issue = raw as Record<string, unknown>
    if (typeof issue.id !== "string" || !issueKinds.has(issue.kind as MetaIssueKind)) {
      throw new Error("META_REVIEW_ISSUE_ID")
    }
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
    if (typeof issue.statement !== "string") throw new Error("META_REVIEW_STATEMENT")
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
