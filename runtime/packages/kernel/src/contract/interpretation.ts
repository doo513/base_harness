import type { InterpretationProposal, UncertaintyCandidate, UncertaintyKind, DecisionImpact, CandidateSourceReference as SourceReference } from "@base-harness/domain-contracts"

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

function requiredInterpretationString(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) throw new Error(`INTERPRETATION_STRING:${field}`)
  return value
}

function optionalInterpretationString(value: unknown): string | undefined {
  return value === undefined ? undefined : requiredInterpretationString(value, "optional")
}

function interpretationStringArray(value: unknown): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string" && item.trim().length > 0)) {
    throw new Error("INTERPRETATION_ID_LIST")
  }
  return [...value]
}

