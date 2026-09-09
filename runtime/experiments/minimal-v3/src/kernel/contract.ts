import { createHash, randomUUID } from "node:crypto"
import { join } from "node:path"
import type { HarnessConfig, LoadedConfig, VerifierConfig } from "../config"
import type { ToolRegistry } from "../tools/registry"
import type { Risk } from "../types"

export interface ContractProposal {
  goal: string
  criteria: Array<{ id: string; statement: string; claimIds: string[]; required: boolean; risk: Risk }>
  claims: Array<{
    id: string
    criterionIds: string[]
    statement: string
    kind: "artifact" | "execution" | "behavior" | "configuration" | "negative" | "external"
    targets: string[]
    capabilities: string[]
    exclusions?: string[]
    minimumStrength: "structural" | "execution" | "behavioral" | "external_oracle"
    allowedVerifierIds: string[]
    minIndependentFamilies: number
  }>
  constraints?: string[]
}

export const contractToolSchema = {
  type: "object", additionalProperties: false, required: ["goal", "criteria", "claims"],
  properties: {
    goal: { type: "string" },
    criteria: { type: "array", items: { type: "object", additionalProperties: false, required: ["id", "statement", "claimIds", "required", "risk"], properties: { id: { type: "string" }, statement: { type: "string" }, claimIds: { type: "array", items: { type: "string" } }, required: { type: "boolean" }, risk: { type: "string", enum: ["low", "medium", "high", "critical"] } } },
    claims: { type: "array", items: { type: "object", additionalProperties: false, required: ["id", "criterionIds", "statement", "kind", "targets", "capabilities", "minimumStrength", "allowedVerifierIds", "minIndependentFamilies"], properties: { id: { type: "string" }, criterionIds: { type: "array", items: { type: "string" } }, statement: { type: "string" }, kind: { type: "string", enum: ["artifact", "execution", "behavior", "configuration", "negative", "external"] }, targets: { type: "array", items: { type: "string" } }, capabilities: { type: "array", items: { type: "string" } }, exclusions: { type: "array", items: { type: "string" } }, minimumStrength: { type: "string", enum: ["structural", "execution", "behavioral", "external_oracle"] }, allowedVerifierIds: { type: "array", items: { type: "string" } }, minIndependentFamilies: { type: "number" } } } },
    constraints: { type: "array", items: { type: "string" } },
  },
} as const

const sha = (value: string | Uint8Array): string => createHash("sha256").update(value).digest("hex")

export function verifierCatalog(verifiers: VerifierConfig[]) {
  return verifiers.map(({ id, strength, claimKinds, methodId, deterministicOracle }) => ({ id, strength, claimKinds, methodId, deterministicOracle: !!deterministicOracle }))
}

export async function materializeContract(input: {
  proposal: ContractProposal
  originalRequest: string
  revision: number
  contractId?: string
  workspace: string
  provider: string
  model: string
  loaded: LoadedConfig
  tools: ToolRegistry
}): Promise<Record<string, unknown>> {
  validateProposal(input.proposal, input.loaded.config)
  const source = { sourceId: "user-root", sourceType: "user_message", text: input.originalRequest }
  const sourceRef = { sourceId: source.sourceId, sourceType: source.sourceType, sha256: sha(source.text) }
  const lockFiles = ["bun.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "pyproject.toml"]
  let lockMaterial = ""
  for (const name of lockFiles) {
    const file = Bun.file(join(input.workspace, name))
    if (await file.exists()) lockMaterial += name + "\0" + await file.text()
  }
  const workspaceRevision = sha(input.workspace + "\0" + lockMaterial)
  return {
    schemaVersion: "goal-contract-v2",
    contractId: input.contractId ?? `contract-${randomUUID()}`,
    revision: input.revision,
    goal: input.proposal.goal,
    sourceRefs: [sourceRef],
    criteria: input.proposal.criteria.map((item) => ({ criterionId: item.id, statement: item.statement, sourceRefs: [sourceRef], claimIds: item.claimIds, required: item.required, risk: item.risk })),
    claims: input.proposal.claims.map((item) => ({
      claimId: item.id,
      criterionIds: item.criterionIds,
      origin: "user",
      statement: item.statement,
      kind: item.kind,
      scope: { targets: item.targets, capabilities: item.capabilities, exclusions: item.exclusions ?? [] },
      applicability: {
        os: process.platform,
        arch: process.arch,
        runtime: `bun-${Bun.version}`,
        provider: input.provider,
        model: input.model,
        tools: Object.fromEntries(input.tools.list().map((tool) => [tool.name, "runtime-v3"])),
        dependencyLockHash: sha(lockMaterial || "no-lock"),
        configHash: input.loaded.digest,
        workspaceRevision,
      },
      predicate: { type: "command_exit", expectedExitCode: 0 },
      verifierPolicy: { minimumStrength: item.minimumStrength, allowedVerifierIds: item.allowedVerifierIds, minIndependentFamilies: item.minIndependentFamilies },
    })),
    constraints: [...(input.proposal.constraints ?? []), "Ready is verifier-owned."],
  }
}

function validateProposal(proposal: ContractProposal, config: HarnessConfig): void {
  if (!proposal.goal?.trim() || !proposal.criteria?.length || !proposal.claims?.length) throw new Error("GoalContract requires a goal, criteria and claims")
  const claims = new Set(proposal.claims.map((item) => item.id))
  const criteria = new Set(proposal.criteria.map((item) => item.id))
  if (claims.size !== proposal.claims.length || criteria.size !== proposal.criteria.length) throw new Error("GoalContract IDs must be unique")
  const verifierIds = new Set(config.verification.verifiers.map((item) => item.id))
  for (const criterion of proposal.criteria) if (!criterion.claimIds.length || criterion.claimIds.some((id) => !claims.has(id))) throw new Error(`Criterion ${criterion.id} has invalid Claim bindings`)
  for (const claim of proposal.claims) {
    if (!claim.criterionIds.length || claim.criterionIds.some((id) => !criteria.has(id))) throw new Error(`Claim ${claim.id} has invalid Criterion bindings`)
    if (!claim.targets.length || !claim.capabilities.length) throw new Error(`Claim ${claim.id} needs scope targets and capabilities`)
    if (!claim.allowedVerifierIds.length || claim.allowedVerifierIds.some((id) => !verifierIds.has(id))) throw new Error(`Claim ${claim.id} references an unavailable verifier`)
    if (!Number.isInteger(claim.minIndependentFamilies) || claim.minIndependentFamilies < 1) throw new Error(`Claim ${claim.id} has invalid evidence family count`)
  }
}
