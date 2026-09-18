import type {
  ContractReviewPolicy, ContractReviewFacts, ContractReviewDecision, PreflightReason,
  UncertaintyCandidate, ReadonlyValue,
} from "@base-harness/domain-contracts"

function reasonForCandidate(candidate: ReadonlyValue<UncertaintyCandidate>): PreflightReason {
  if (candidate.impact === "scope") return "scope_conflict"
  if (candidate.impact === "verifier_applicability") return "verifier_mismatch"
  if (candidate.impact === "external_effect") return "external_side_effect"
  if (candidate.kind === "multiple_interpretations") return "multiple_valid_interpretations"
  if (candidate.kind === "missing_decision") return "missing_required_value"
  return "unsafe_default"
}

/** Compatibility policy. Uses only the existing typed uncertainty and risk facts. */
export const defaultContractReviewPolicy: ContractReviewPolicy = {
  evaluate(facts) {
    const { interpretation, signals } = structuredClone(facts) as ContractReviewFacts
    const requiredDecisions = interpretation.candidates.filter((candidate) => candidate.impact !== "implementation_choice")
    const assumptions = interpretation.candidates.filter((candidate) => candidate.impact === "implementation_choice")
    const reasons: PreflightReason[] = []
    if (requiredDecisions.length) reasons.push(...requiredDecisions.map(reasonForCandidate))
    else {
      if (signals.risk === "high" || signals.risk === "critical") reasons.push("high_risk")
      if (signals.configuredProfile === "strict") reasons.push("strict_profile")
      if (signals.hasExternalClaim) reasons.push("external_side_effect")
      if (!signals.applicabilityResolved) reasons.push("applicability_gap")
      if (signals.requiredClaimCount > 1 || signals.requiredCriterionCount > 1) reasons.push("complex_contract")
    }
    return {
      decision: requiredDecisions.length ? "needs_input" : reasons.length ? "meta_review_required" : "proceed",
      reasons: [...new Set(reasons)], requiredDecisions, assumptions,
      affectedClaimIds: [...new Set(requiredDecisions.flatMap((candidate) => candidate.affectedClaimIds))],
      affectedCriterionIds: [...new Set(requiredDecisions.flatMap((candidate) => candidate.affectedCriterionIds))],
    }
  },
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value)
    for (const child of Object.values(value)) freeze(child)
  }
  return value
}

export function reviewContractFacts(facts: ContractReviewFacts, policy: ContractReviewPolicy = defaultContractReviewPolicy): ContractReviewDecision {
  const decision = policy.evaluate(freeze(structuredClone(facts)))
  if (!decision || !["proceed", "needs_input", "meta_review_required"].includes(decision.decision)
    || !Array.isArray(decision.reasons) || !Array.isArray(decision.requiredDecisions) || !Array.isArray(decision.assumptions)
    || !Array.isArray(decision.affectedClaimIds) || !Array.isArray(decision.affectedCriterionIds)
    || (decision.decision === "needs_input" && !decision.requiredDecisions.length)) {
    throw new Error("CONTRACT_REVIEW_POLICY_RESULT")
  }
  return structuredClone(decision)
}
