import type { ContractPrepareResult, ContractPreflightSignals } from "@base-harness/domain-contracts"
import { parseInterpretationProposal } from "./interpretation"
import type { ContractBody, DomainPolicySnapshot, ReadonlyValue } from "@base-harness/domain-contracts"
import type { PreparedContract } from "./types"

function object(value: unknown, field: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error(`CONTRACT_SCHEMA:${field}`)
  return value as Record<string, unknown>
}

function string(value: unknown, field: string): asserts value is string {
  if (typeof value !== "string") throw new Error(`CONTRACT_SCHEMA:${field}`)
}

function strings(value: unknown, field: string): asserts value is string[] {
  if (!Array.isArray(value) || [...value].some((item) => typeof item !== "string")) {
    throw new Error(`CONTRACT_SCHEMA:${field}`)
  }
}

/** Decode shape only. Required content and relationships are checked by Validate. */
export function parseContractBody(value: unknown): ContractBody {
  const body = object(value, "body")
  string(body.goal, "goal")
  if (!Array.isArray(body.claims) || !Array.isArray(body.criteria)) throw new Error("CONTRACT_SCHEMA")
  if (body.constraints !== undefined) strings(body.constraints, "constraints")
  for (const raw of body.criteria) {
    const item = object(raw, "criterion")
    string(item.criterionId, "criterionId")
    string(item.statement, "criterion.statement")
    strings(item.claimIds, "criterion.claimIds")
    if (typeof item.required !== "boolean") throw new Error("CONTRACT_SCHEMA:criterion.required")
    if (!["low", "medium", "high", "critical"].includes(String(item.risk))) throw new Error("CONTRACT_SCHEMA:risk")
    if (item.verificationTemplate !== undefined) string(item.verificationTemplate, "verificationTemplate")
  }
  for (const raw of body.claims) {
    const item = object(raw, "claim")
    string(item.claimId, "claimId")
    string(item.statement, "claim.statement")
    strings(item.criterionIds, "claim.criterionIds")
    if (!["user", "harness_policy", "derived_dependency"].includes(String(item.origin))) throw new Error("CONTRACT_SCHEMA:origin")
    if (!["artifact", "execution", "behavior", "configuration", "negative", "external"].includes(String(item.kind))) {
      throw new Error("CONTRACT_SCHEMA:kind")
    }
    const scope = object(item.scope, "scope")
    strings(scope.targets, "scope.targets")
    strings(scope.capabilities, "scope.capabilities")
    strings(scope.exclusions, "scope.exclusions")
    const predicate = object(item.predicate, "predicate")
    string(predicate.type, "predicate.type")
    const policy = object(item.verifierPolicy, "verifierPolicy")
    if (!["structural", "execution", "behavioral", "external_oracle"].includes(String(policy.minimumStrength))) {
      throw new Error("CONTRACT_SCHEMA:minimumStrength")
    }
    strings(policy.allowedVerifierIds, "allowedVerifierIds")
    if (!Number.isInteger(policy.minIndependentFamilies) || Number(policy.minIndependentFamilies) < 1) {
      throw new Error("CONTRACT_SCHEMA:minIndependentFamilies")
    }
    if (item.applicability !== undefined) {
      const applicability = object(item.applicability, "applicability")
      for (const key of ["os", "arch", "runtime", "provider", "model", "dependencyLockHash", "configHash", "workspaceRevision"]) {
        if (applicability[key] !== undefined) string(applicability[key], `applicability.${key}`)
      }
      if (applicability.tools !== undefined) {
        for (const version of Object.values(object(applicability.tools, "applicability.tools"))) string(version, "tool version")
      }
    }
  }
  return body as unknown as ContractBody
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value)
    for (const child of Object.values(value)) freeze(child)
  }
  return value
}

/** Copies the submission and selected metadata. No Host state or authority is accepted. */
export function prepareContract(
  proposal: unknown,
  policy: ReadonlyValue<DomainPolicySnapshot>,
  configuredProfile: ContractPreflightSignals["configuredProfile"],
): PreparedContract {
  const input = object(structuredClone(proposal), "proposal")
  for (const key of Object.keys(input)) {
    if (!["goal", "criteria", "claims", "constraints", "interpretation"].includes(key)) {
      throw new Error(`CONTRACT_SUBMISSION_FIELD:${key}`)
    }
  }
  const { interpretation, ...body } = input
  // Legacy evidence-family aliases and omitted exclusions are normalized at this boundary only.
  if (Array.isArray(body.claims)) for (const raw of body.claims) {
    if (!raw || typeof raw !== "object") continue
    const claim = raw as Record<string, any>
    if (claim.scope && claim.scope.exclusions === undefined) claim.scope.exclusions = []
    if (claim.verifierPolicy && claim.verifierPolicy.minIndependentFamilies === undefined) {
      const count = claim.verifierPolicy.minimumIndependentFamilies ?? claim.verifierPolicy.minimumEvidenceFamilies
      if (count !== undefined) claim.verifierPolicy.minIndependentFamilies = count
    }
  }
  const contract = parseContractBody(body)
  const snapshot = structuredClone(policy)
  for (const criterion of contract.criteria) {
    if (criterion.verificationTemplate === undefined && snapshot.verification.criterionTemplates.length) {
      criterion.verificationTemplate = snapshot.verification.criterionTemplates[0]
    }
  }
  return freeze({
    stage: "prepare", body: contract,
    interpretation: parseInterpretationProposal(interpretation),
    policy: snapshot, configuredProfile,
  })
}

export function prepareContractPreflight(
  proposal: unknown,
  signals: ContractPreflightSignals,
): ContractPrepareResult {
  return {
    stage: "prepare",
    interpretation: parseInterpretationProposal(proposal),
    signals: { ...signals },
  }
}
