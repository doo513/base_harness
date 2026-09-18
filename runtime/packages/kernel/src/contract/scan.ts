import type { ContractPrepareResult, ContractScanBindings, ContractScanResult } from "@base-harness/domain-contracts"
import { validateInterpretationBindings } from "./interpretation"
import type { PreparedContract, ScannedContract } from "./types"

/** Collect explicit fields and edges only; no natural-language classification. */
export function scanContract(input: PreparedContract): ScannedContract {
  const prepared = structuredClone(input)
  const { claims, criteria } = prepared.body
  const order = { low: 0, medium: 1, high: 2, critical: 3 } as const
  let risk: keyof typeof order = "low"
  for (const criterion of criteria) if (order[criterion.risk] > order[risk]) risk = criterion.risk
  const legacyClaims = claims as Array<typeof claims[number] & {
    required?: boolean; external?: boolean; scope: { external?: boolean }; applicability?: { status?: string }
  }>
  return {
    ...prepared, stage: "scan",
    claimIds: claims.map((claim) => claim.claimId),
    criterionIds: criteria.map((criterion) => criterion.criterionId),
    links: [
      ...claims.flatMap((claim) => claim.criterionIds.map((to) => ({ from: claim.claimId, to, fromKind: "claim" as const }))),
      ...criteria.flatMap((criterion) => criterion.claimIds.map((to) => ({ from: criterion.criterionId, to, fromKind: "criterion" as const }))),
    ],
    signals: {
      risk, configuredProfile: prepared.configuredProfile,
      requiredClaimCount: legacyClaims.filter((claim) => claim.required !== false).length,
      requiredCriterionCount: criteria.filter((criterion) => criterion.required).length,
      hasExternalClaim: legacyClaims.some((claim) => claim.kind === "external" || claim.external === true || claim.scope.external === true),
      applicabilityResolved: legacyClaims.every((claim) => claim.applicability !== undefined && claim.applicability.status !== "unresolved"),
    },
  }
}

export function scanContractPreflight(
  prepared: ContractPrepareResult,
  bindings?: ContractScanBindings,
): ContractScanResult {
  if (bindings) {
    validateInterpretationBindings(prepared.interpretation, bindings.claimIds, bindings.criterionIds)
  }
  prepared = structuredClone(prepared)
  const candidates = prepared.interpretation.candidates
  return {
    stage: "scan",
    interpretation: prepared.interpretation,
    signals: prepared.signals,
    consequentialCandidates: candidates.filter((candidate) => candidate.impact !== "implementation_choice"),
    assumptionCandidates: candidates.filter((candidate) => candidate.impact === "implementation_choice"),
  }
}
