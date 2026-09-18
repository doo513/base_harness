import type { ContractScanResult, ContractValidateDedupeResult, ContractReviewPolicy } from "@base-harness/domain-contracts"
import type { ContractBody } from "@base-harness/domain-contracts"
import type { ContractDiagnostic, ContractStructureResult, ScannedContract } from "./types"
import { parseContractBody } from "./prepare"
import { reviewContractFacts } from "./review-policy"

/** Exact diagnostic identity only. Merging never discards provenance or targets. */
export function dedupeContractDiagnostics(diagnostics: ContractDiagnostic[]): ContractDiagnostic[] {
  const result = new Map<string, ContractDiagnostic>()
  for (const raw of diagnostics) {
    const key = JSON.stringify([raw.code, raw.message])
    const previous = result.get(key)
    if (!previous) { result.set(key, structuredClone(raw)); continue }
    for (const field of ["paths", "issueIds", "affectedClaimIds", "affectedCriterionIds"] as const) {
      previous[field] = [...new Set([...previous[field], ...raw[field]])]
    }
    previous.sourceRefs = [...new Map([...previous.sourceRefs, ...raw.sourceRefs].map((ref) => [JSON.stringify(ref), structuredClone(ref)])).values()]
  }
  return [...result.values()]
}

function bodyDiagnostics(body: ContractBody): ContractDiagnostic[] {
  const diagnostics: ContractDiagnostic[] = []
  const add = (code: string, field: string, claims: string[] = [], criteria: string[] = []) => {
    diagnostics.push({ code, message: code, paths: [field], issueIds: [], affectedClaimIds: claims, affectedCriterionIds: criteria, sourceRefs: [] })
  }
  const nonempty = (value: string) => value.trim().length > 0
  const list = (values: string[]) => values.length > 0 && values.every(nonempty)
  if (!nonempty(body.goal)) add("CONTRACT_GOAL", "goal")
  if (!body.claims.length || !body.criteria.length) add("CONTRACT_EMPTY", "body")
  if (body.constraints?.some((value) => !nonempty(value))) add("CONTRACT_CONSTRAINT", "constraints")
  const claims = new Map<string, ContractBody["claims"][number]>()
  const criteria = new Map<string, ContractBody["criteria"][number]>()
  for (const [i, claim] of body.claims.entries()) {
    const at = `claims[${i}]`
    if (!nonempty(claim.claimId) || claim.claimId.trim() !== claim.claimId || claims.has(claim.claimId)) add("CONTRACT_CLAIM_ID", at, [claim.claimId])
    claims.set(claim.claimId, claim)
    if (!nonempty(claim.statement) || !list(claim.criterionIds) || !list(claim.scope.targets) || !list(claim.scope.capabilities)
      || !list(claim.verifierPolicy.allowedVerifierIds) || !nonempty(claim.predicate.type)
      || claim.scope.exclusions.some((value) => !nonempty(value))) add("CONTRACT_CLAIM_REQUIRED", at, [claim.claimId])
    if (new Set(claim.criterionIds).size !== claim.criterionIds.length) add("CONTRACT_DUPLICATE_REFERENCE", at, [claim.claimId], claim.criterionIds)
  }
  for (const [i, criterion] of body.criteria.entries()) {
    const at = `criteria[${i}]`
    if (!nonempty(criterion.criterionId) || criterion.criterionId.trim() !== criterion.criterionId || criteria.has(criterion.criterionId)) add("CONTRACT_CRITERION_ID", at, [], [criterion.criterionId])
    criteria.set(criterion.criterionId, criterion)
    if (!nonempty(criterion.statement) || !list(criterion.claimIds)) add("CONTRACT_CRITERION_REQUIRED", at, [], [criterion.criterionId])
    if (new Set(criterion.claimIds).size !== criterion.claimIds.length) add("CONTRACT_DUPLICATE_REFERENCE", at, criterion.claimIds, [criterion.criterionId])
  }
  for (const claim of body.claims) for (const id of claim.criterionIds) {
    if (!criteria.get(id)?.claimIds.includes(claim.claimId)) add("CONTRACT_BINDING", `claim:${claim.claimId}`, [claim.claimId], [id])
  }
  for (const criterion of body.criteria) for (const id of criterion.claimIds) {
    if (!claims.get(id)?.criterionIds.includes(criterion.criterionId)) add("CONTRACT_BINDING", `criterion:${criterion.criterionId}`, [id], [criterion.criterionId])
  }
  return diagnostics
}

export function validateContract(input: ScannedContract): ContractStructureResult {
  const scanned = structuredClone(input)
  const diagnostics = bodyDiagnostics(scanned.body)
  for (const candidate of scanned.interpretation.candidates) {
    const codes: string[] = []
    if (!candidate.affectedClaimIds.length && !candidate.affectedCriterionIds.length) codes.push("INTERPRETATION_UNBOUND")
    if (candidate.affectedClaimIds.some((id) => !scanned.claimIds.includes(id))) codes.push("INTERPRETATION_UNKNOWN_CLAIM")
    if (candidate.affectedCriterionIds.some((id) => !scanned.criterionIds.includes(id))) codes.push("INTERPRETATION_UNKNOWN_CRITERION")
    for (const code of codes) diagnostics.push({
      code, message: code, paths: [`interpretation:${candidate.id}`], issueIds: [candidate.id],
      affectedClaimIds: candidate.affectedClaimIds, affectedCriterionIds: candidate.affectedCriterionIds,
      sourceRefs: candidate.sourceRefs,
    })
  }
  const templates = scanned.policy.verification.criterionTemplates
  for (const criterion of scanned.body.criteria) if (templates.length && !templates.includes(criterion.verificationTemplate ?? "")) {
    diagnostics.push({ code: "DOMAIN_CRITERION_TEMPLATE", message: "DOMAIN_CRITERION_TEMPLATE", paths: [`criterion:${criterion.criterionId}`], issueIds: [], affectedClaimIds: criterion.claimIds, affectedCriterionIds: [criterion.criterionId], sourceRefs: [] })
  }
  const common = { stage: "validate_dedupe" as const, signals: scanned.signals, diagnostics: dedupeContractDiagnostics(diagnostics) }
  if (diagnostics.length) return { ...common, valid: false }
  return { ...common, valid: true, candidate: { body: scanned.body, interpretation: scanned.interpretation, policy: scanned.policy } }
}

/** Compatibility check for stored bodies; no interpretation or restore policy is inferred. */
export function assertContractProposal(value: unknown): asserts value is ContractBody {
  const diagnostics = dedupeContractDiagnostics(bodyDiagnostics(parseContractBody(structuredClone(value))))
  if (diagnostics.length) throw Object.assign(new Error(diagnostics[0]!.code), { code: diagnostics[0]!.code, diagnostics })
}

/** Compatibility facade: structure is handled by validateContract; this returns policy advice. */
export function validateAndDedupeContractPreflight(
  scanned: ContractScanResult,
  policy?: ContractReviewPolicy,
): ContractValidateDedupeResult {
  const reviewDecision = reviewContractFacts(scanned, policy)
  return {
    stage: "validate_dedupe",
    interpretation: structuredClone(scanned.interpretation),
    signals: { ...scanned.signals },
    scannedCandidateCount: scanned.interpretation.candidates.length,
    reviewDecision,
    result: {
      version: 1,
      decision: reviewDecision.decision === "proceed" ? "accept" : reviewDecision.decision,
      reasons: reviewDecision.reasons,
      affectedClaimIds: reviewDecision.affectedClaimIds,
      affectedCriterionIds: reviewDecision.affectedCriterionIds,
      // Pure checks cannot grant mutation. The Host sets this after Runtime acceptance.
      mutatingActionAllowed: false,
    },
  }
}
