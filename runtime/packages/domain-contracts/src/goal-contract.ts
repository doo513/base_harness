import type { DomainPolicySnapshot, ReadonlyValue, VerificationStrength } from "./domain"

/** Shared data only. A materialized wire contract is not Runtime acceptance or Evidence. */
export type ClaimKind = "artifact" | "execution" | "behavior" | "configuration" | "negative" | "external"
export type Risk = "low" | "medium" | "high" | "critical"

export interface GoalSource {
  sourceId: string
  sourceType: "user_message" | "session_title" | "harness_policy"
  text: string
}

export interface VerifierSourceReference {
  sourceId: string
  sourceType: GoalSource["sourceType"]
  sha256: string
}

export interface Applicability {
  os: string
  arch: string
  runtime: string
  provider: string
  model: string
  tools: Record<string, string>
  dependencyLockHash: string
  configHash: string
  workspaceRevision: string
}

export interface CriterionContract {
  criterionId: string
  statement: string
  verificationTemplate?: string
  sourceRefs: VerifierSourceReference[]
  claimIds: string[]
  required: boolean
  risk: Risk
}

export interface ClaimContract {
  claimId: string
  criterionIds: string[]
  origin: "user" | "harness_policy" | "derived_dependency"
  statement: string
  kind: ClaimKind
  scope: {
    targets: string[]
    capabilities: string[]
    exclusions: string[]
  }
  applicability: Applicability
  predicate: {
    type: "command_exit" | "output_contains" | string
    expectedExitCode?: number
    stream?: "stdout" | "stderr"
    value?: string
  }
  verifierPolicy: {
    minimumStrength: VerificationStrength
    allowedVerifierIds: string[]
    minIndependentFamilies: number
  }
}

export interface GoalContract {
  schemaVersion: "goal-contract-v2"
  contractId: string
  revision: number
  goal: string
  sourceRefs: VerifierSourceReference[]
  criteria: CriterionContract[]
  claims: ClaimContract[]
  constraints: string[]
}

export interface ContractBody {
  goal: string
  criteria: Array<{
    criterionId: string
    statement: string
    verificationTemplate?: string
    claimIds: string[]
    required: boolean
    risk: Risk
  }>
  claims: Array<Omit<ClaimContract, "applicability"> & { applicability?: Partial<Applicability> }>
  constraints?: string[]
}

export type GoalContractProposal = ContractBody

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

export interface CandidateSourceReference {
  source: string
  pointer?: string
  quote?: string
}

export interface MetaReviewIssue {
  id: string
  kind: MetaIssueKind
  severity: "blocking" | "warning"
  targetIds: string[]
  sourceRefs: CandidateSourceReference[]
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
  sourceRefs: CandidateSourceReference[]
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

export type ContractPipelineStage = "prepare" | "scan" | "validate_dedupe"

export interface ContractPrepareResult {
  stage: "prepare"
  interpretation: InterpretationProposal
  signals: ContractPreflightSignals
}

export interface ContractScanBindings {
  claimIds: readonly string[]
  criterionIds: readonly string[]
}

export interface ContractScanResult {
  stage: "scan"
  interpretation: InterpretationProposal
  signals: ContractPreflightSignals
  consequentialCandidates: UncertaintyCandidate[]
  assumptionCandidates: UncertaintyCandidate[]
}

export interface ContractValidateDedupeResult {
  stage: "validate_dedupe"
  interpretation: InterpretationProposal
  signals: ContractPreflightSignals
  scannedCandidateCount: number
  result: ContractPreflightResult
  reviewDecision?: ContractReviewDecision
}

export interface ContractReviewFacts {
  interpretation: InterpretationProposal
  signals: ContractPreflightSignals
}

/** Policy advice only; Runtime acceptance and tool permission are separate checks. */
export interface ContractReviewDecision {
  decision: "proceed" | "meta_review_required" | "needs_input"
  reasons: PreflightReason[]
  affectedClaimIds: string[]
  affectedCriterionIds: string[]
  requiredDecisions: UncertaintyCandidate[]
  assumptions: UncertaintyCandidate[]
}

export interface ContractReviewPolicy {
  evaluate(facts: ReadonlyValue<ContractReviewFacts>): ContractReviewDecision
}


/** Model-authored proposal; no Host answers, acceptance flags or execution authority. */
export interface ContractSubmission extends ContractBody {
  interpretation: InterpretationProposal
}

export interface ContractCandidate {
  body: ContractBody
  interpretation: InterpretationProposal
}

/** A structurally checked candidate, still subject to review and Runtime acceptance. */
export interface ValidatedContractCandidate extends ContractCandidate {
  policy: ReadonlyValue<DomainPolicySnapshot>
}

export type ContractProcessingOutcome =
  | "checking" | "needs_input" | "revision_required" | "reviewing"
  | "awaiting_runtime" | "accepted" | "rejected" | "error"

export interface ContractQuestionIssue {
  id: string
  statement: string
  suggestedResolution?: string
  sourceRefs: CandidateSourceReference[]
  affectedClaimIds: string[]
  affectedCriterionIds: string[]
}

export interface ContractQuestionBatch {
  id: string
  sessionID: string
  runId: string
  candidateRevision: number
  contentHash: string
  issues: ContractQuestionIssue[]
  status: "pending" | "answered" | "partial" | "cancelled"
}

/** Created only from the Host's Question service response, never parsed from a submission. */
export interface HostContractAnswer {
  batchId: string
  issueId: string
  answer: string[]
}

/** Ephemeral current-Run context. Persistence is not a source of answer authority. */
export interface HostContractContext {
  sessionID: string
  runId: string
  originalRequest: string
  candidateRevision: number
  contentHash: string
  candidate: ContractCandidate
  outcome: ContractProcessingOutcome
  issues: ContractQuestionIssue[]
  questions: ContractQuestionBatch[]
  answers: HostContractAnswer[]
}
