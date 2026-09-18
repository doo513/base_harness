import type { GoalContract, Risk } from "@base-harness/domain-contracts"

export function acceptedContract(
  claimIds: readonly string[],
  criterionIds: readonly string[],
  options: { target?: string; risk?: Risk } = {},
): Pick<GoalContract, "claims" | "criteria"> {
  if (claimIds.length !== criterionIds.length) throw new Error("Contract fixture requires one Criterion per Claim")
  const target = options.target ?? "."
  const risk = options.risk ?? "low"
  return {
    criteria: criterionIds.map((criterionId, index) => ({
      criterionId,
      statement: "Fixture criterion",
      sourceRefs: [],
      claimIds: [claimIds[index]!],
      required: true,
      risk,
    })),
    claims: claimIds.map((claimId, index) => ({
      claimId,
      criterionIds: [criterionIds[index]!],
      origin: "user" as const,
      statement: "Fixture claim",
      kind: "artifact" as const,
      scope: { targets: [target], capabilities: ["write"], exclusions: [] },
      applicability: {
        os: "test",
        arch: "test",
        runtime: "test",
        provider: "test",
        model: "test",
        tools: {},
        dependencyLockHash: "test",
        configHash: "test",
        workspaceRevision: "test",
      },
      predicate: { type: "exists" as const },
      verifierPolicy: {
        minimumStrength: "structural" as const,
        allowedVerifierIds: ["test"],
        minIndependentFamilies: 1,
      },
    })),
  }
}
