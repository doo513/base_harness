import { Coordinator, Orchestration, type GoalContractProposal } from "../harness/coordinator-service"

export interface HarnessContractProposal {
  goal: string
  criteria: Array<{
    criterionId: string
    statement: string
    claimIds: string[]
    required: boolean
    risk: "low" | "medium" | "high" | "critical"
  }>
  claims: Array<{
    claimId: string
    criterionIds: string[]
    origin: "user" | "harness_policy" | "derived_dependency"
    statement: string
    kind: "artifact" | "execution" | "behavior" | "configuration" | "negative" | "external"
    scope: { targets: string[]; capabilities: string[]; exclusions: string[] }
    applicability?: Record<string, unknown>
    predicate: Record<string, unknown>
    verifierPolicy: {
      minimumStrength: "structural" | "execution" | "behavioral" | "external_oracle"
      allowedVerifierIds: string[]
      minIndependentFamilies: number
    }
  }>
  constraints?: string[]
}

const submitted = new Set<string>()
const preContractTools = new Set([
  "harness_contract",
  "read",
  "glob",
  "grep",
  "webfetch",
  "websearch",
  "skill",
  "question",
  "todowrite",
  "lsp",
  "invalid",
  "plan_exit",
])

export function assertHarnessContractSubmitted(sessionID: string, toolID: string) {
  if (
    preContractTools.has(toolID) ||
    submitted.has(sessionID) ||
    Orchestration.hasContract(sessionID) ||
    Orchestration.canUseBeforeContract(sessionID, toolID)
  )
    return
  throw new Error(
    "GoalContract is required before state-changing tools. Use harness_contract after read-only discovery.",
  )
}

function validateProposal(params: HarnessContractProposal) {
  const criteria = new Map(params.criteria.map((item) => [item.criterionId, item]))
  const claims = new Map(params.claims.map((item) => [item.claimId, item]))
  if (criteria.size !== params.criteria.length) throw new Error("GoalContract has duplicate criterionId values")
  if (claims.size !== params.claims.length) throw new Error("GoalContract has duplicate claimId values")
  if (criteria.size === 0 || claims.size === 0) throw new Error("GoalContract requires criteria and claims")
  for (const criterion of criteria.values()) {
    if (!criterion.statement.trim() || criterion.claimIds.length === 0) {
      throw new Error("Every Criterion requires a statement and at least one Claim")
    }
    for (const claimID of criterion.claimIds) {
      const claim = claims.get(claimID)
      if (!claim || !claim.criterionIds.includes(criterion.criterionId)) {
        throw new Error("Criterion-Claim binding must be bidirectional")
      }
    }
  }
  for (const claim of claims.values()) {
    if (
      !claim.statement.trim() ||
      claim.criterionIds.length === 0 ||
      claim.scope.targets.length === 0 ||
      claim.scope.capabilities.length === 0 ||
      claim.verifierPolicy.allowedVerifierIds.length === 0
    ) {
      throw new Error("Every Claim requires statement, Criterion, Scope and VerifierPolicy")
    }
    for (const criterionID of claim.criterionIds) {
      if (!criteria.get(criterionID)?.claimIds.includes(claim.claimId)) {
        throw new Error("Claim-Criterion binding must be bidirectional")
      }
    }
  }
}

export async function registerHarnessContractProposal(
  sessionID: string,
  params: HarnessContractProposal,
) {
  validateProposal(params)
  submitted.add(sessionID)
  Orchestration.registerContract(
    sessionID,
    params.claims.map((item) => item.claimId),
    params.criteria.map((item) => item.criterionId),
  )
  await Coordinator.proposeContract(sessionID, params as unknown as GoalContractProposal)
}
