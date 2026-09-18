import type {
  ContractCandidate, ContractPreflightSignals, DomainPolicySnapshot,
  CandidateSourceReference, ReadonlyValue, ValidatedContractCandidate,
} from "@base-harness/domain-contracts"

export interface PreparedContract extends ContractCandidate {
  stage: "prepare"
  policy: ReadonlyValue<DomainPolicySnapshot>
  configuredProfile: ContractPreflightSignals["configuredProfile"]
}

export interface ScannedContract extends Omit<PreparedContract, "stage"> {
  stage: "scan"
  signals: ContractPreflightSignals
  claimIds: string[]
  criterionIds: string[]
  links: Array<{ from: string; to: string; fromKind: "claim" | "criterion" }>
}

export interface ContractDiagnostic {
  code: string
  message: string
  paths: string[]
  issueIds: string[]
  affectedClaimIds: string[]
  affectedCriterionIds: string[]
  sourceRefs: CandidateSourceReference[]
}

export type ContractStructureResult = {
  stage: "validate_dedupe"
  diagnostics: ContractDiagnostic[]
  signals: ContractPreflightSignals
} & ({ valid: true; candidate: ValidatedContractCandidate } | { valid: false })
