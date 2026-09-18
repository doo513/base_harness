import type { ContractSubmission } from "@base-harness/domain-contracts"

/** Fill unrelated fields in legacy Host lifecycle fixtures with valid contract data. */
export function contractFixture(input: any): ContractSubmission {
  return {
    goal: "Update the requested artifact",
    interpretation: { version: 1, candidates: [] },
    ...input,
    criteria: input.criteria.map((criterion: any) => ({ statement: "The requested artifact exists", required: true, risk: "low", ...criterion })),
    claims: input.claims.map((claim: any) => ({
      statement: "The requested artifact exists", origin: "user", kind: "artifact", predicate: { type: "exists" },
      ...claim,
      scope: { targets: ["input.ts"], capabilities: ["write"], exclusions: [], ...claim.scope },
      verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1, ...claim.verifierPolicy },
    })),
  }
}
