import { createHash } from "node:crypto"

export const SIDECAR_PROTOCOL_VERSION = 4 as const

export type VerificationOutcome =
  | "scope_verified"
  | "ready"
  | "repair"
  | "repair_exhausted"
  | "blocked"
  | "failure"
  | "needs_input"
export type VerificationProfile = "fast" | "adaptive" | "strict"
export type VerificationTrigger = "auto" | "manual"
export type VerificationScopeKind = "root" | "exploration" | "work_unit" | "repair" | "integration"
export type VerificationState =
  | "inactive"
  | "starting"
  | "open"
  | "observing"
  | VerificationOutcome
  | "closed"
export type ClaimResult =
  | "verified"
  | "partial"
  | "refuted"
  | "inconclusive"
  | "not_applicable"
  | "verifier_invalid"
export type ClaimKind = "artifact" | "execution" | "behavior" | "configuration" | "negative" | "external"
export type VerificationStrength = "structural" | "execution" | "behavioral" | "external_oracle"
export type Risk = "low" | "medium" | "high" | "critical"

export interface GoalSource {
  sourceId: string
  sourceType: "user_message" | "session_title" | "harness_policy"
  text: string
}

export interface SourceReference {
  sourceId: string
  sourceType: GoalSource["sourceType"]
  sha256: string
}

export interface Applicability {
  os: string
  arch: string
  runtime: string
  provider: string
  model: string
  tools: Record<string, string>
  dependencyLockHash: string
  configHash: string
  workspaceRevision: string
}

export interface CriterionContract {
  criterionId: string
  statement: string
  sourceRefs: SourceReference[]
  claimIds: string[]
  required: boolean
  risk: Risk
}

export interface ClaimContract {
  claimId: string
  criterionIds: string[]
  origin: "user" | "harness_policy" | "derived_dependency"
  statement: string
  kind: ClaimKind
  scope: {
    targets: string[]
    capabilities: string[]
    exclusions: string[]
  }
  applicability: Applicability
  predicate: {
    type: "command_exit" | "output_contains" | string
    expectedExitCode?: number
    stream?: "stdout" | "stderr"
    value?: string
  }
  verifierPolicy: {
    minimumStrength: VerificationStrength
    allowedVerifierIds: string[]
    minIndependentFamilies: number
  }
}

export interface GoalContract {
  schemaVersion: "goal-contract-v2"
  contractId: string
  revision: number
  goal: string
  sourceRefs: SourceReference[]
  criteria: CriterionContract[]
  claims: ClaimContract[]
  constraints: string[]
}

export interface GoalContractProposal {
  goal: string
  criteria: Array<{
    criterionId: string
    statement: string
    claimIds: string[]
    required: boolean
    risk: Risk
  }>
  claims: Array<Omit<ClaimContract, "applicability"> & { applicability?: Partial<Applicability> }>
  constraints?: string[]
}

export interface ArtifactReference {
  artifactType: string
  sha256: string
  path: string
  trust: "untrusted_execution_observation" | "verifier_observed" | "verifier_attested"
}

export interface CandidateManifest {
  candidateId: string
  runId: string
  scopeId: string
  workUnitId: string
  revision: number
  files: Array<{ path: string; beforeHash: string | null; afterHash: string }>
  patchHash: string
  overlayRoot: string
  candidateWorkspace?: string
}

export interface ScopeAttestation {
  candidateId: string
  candidateRevision: number
  patchHash: string
  artifact?: ArtifactReference
}

export interface CriterionVerificationResult {
  criterionId: string
  result: ClaimResult
  coverage: "full" | "partial" | "none"
  claimIds: string[]
  required: boolean
  risk: Risk
}

export interface ClaimVerificationResult {
  claimId: string
  result: ClaimResult
  coverage: "full" | "partial" | "none"
  evidenceIds: string[]
  familyIds?: string[]
  reason: string
}

export interface EvidenceFamily {
  familyId: string
  methodId: string
  runId: string
  claimId: string
  trustTier: "candidate" | "supported" | "reproduced" | "established"
  /** Verdict for the latest recorded observation of this claim-family. */
  status: "active" | "disputed" | "quarantined"
  /** Absent on legacy artifacts whose status reflected the whole memory case. */
  statusScope?: "verification_observation"
  memoryCaseStatus?: "active" | "disputed" | "quarantined"
  evidenceIds?: string[]
  candidateId?: string
  candidateRevision?: number
  patchHash?: string
}

export interface VerificationStatus {
  state: VerificationState
  goal: string
  runId: string
  scopeId: string
  rootScopeId: string
  contractStatus?: "missing" | "accepted"
  goalContract?: GoalContract | null
  criterionResults: CriterionVerificationResult[]
  claimResults: ClaimVerificationResult[]
  evidenceFamilies: EvidenceFamily[]
  outcome?: VerificationOutcome
  failureKind?: string | null
  failedCriterion?: string | null
  missingEvidence?: string[]
  repairScope?: string | null
  repairScopeId?: string | null
  repairCount?: number
  failureFingerprint?: string
  message?: string
  evidenceRefs: ArtifactReference[]
  candidateRefs: ArtifactReference[]
  readyRef?: ArtifactReference | null
  maxSameFailureRepairs: number
  configuredProfile?: VerificationProfile
  effectiveProfile?: VerificationProfile
  assuranceLevel?: VerificationProfile
  escalationReasons?: string[]
  readyEligible?: boolean
  scopeAttestation?: ScopeAttestation | null
}

export interface ProtocolEnvelope<T = Record<string, unknown>> {
  version: typeof SIDECAR_PROTOCOL_VERSION
  id: string
  runId: string
  scopeId: string
  type: string
  payload: T
}

export interface OpenRunInput {
  runId: string
  scopeId: string
  workspace: string
  goalSources: GoalSource[]
  goalContract?: GoalContract
  configuredProfile?: VerificationProfile
  effectiveProfile?: VerificationProfile
  escalationReasons?: string[]
}

export interface ActionOpenInput {
  scopeId?: string
  actionId?: string
  executionId?: string
  claimIds?: string[]
  tool: string
  input?: unknown
  startedAt?: string
}

export interface ActionCloseInput {
  scopeId?: string
  actionId: string
  status: "completed" | "error"
  output?: unknown
  error?: unknown
  metadata?: Record<string, unknown>
  completedAt?: string
}

export interface ObserveActionInput {
  scopeId?: string
  claimIds?: string[]
  tool: string
  status: "completed" | "error"
  input?: unknown
  output?: unknown
  error?: unknown
  metadata?: Record<string, unknown>
}

export interface VerificationClient {
  readonly runId: string
  readonly rootScopeId: string
  snapshot(): VerificationStatus
  subscribe(listener: (status: VerificationStatus) => void): () => void
  open(input: OpenRunInput): Promise<VerificationStatus>
  openScope(
    scopeId: string,
    parentScopeId: string,
    options?: { kind?: VerificationScopeKind; assignedClaimIds?: string[] },
  ): Promise<VerificationStatus>
  proposeContract(contract: GoalContract, scopeId?: string): Promise<VerificationStatus>
  amendContract(contract: GoalContract, scopeId?: string): Promise<VerificationStatus>
  openAction(input: ActionOpenInput): Promise<{ actionId: string; status: VerificationStatus }>
  closeAction(input: ActionCloseInput): Promise<VerificationStatus>
  observe(input: ObserveActionInput): Promise<VerificationStatus>
  verify(
    reason: "automatic" | "manual" | "completion",
    scopeId?: string,
    target?: { claimIds?: string[]; criterionIds?: string[] },
  ): Promise<VerificationStatus>
  attachCandidate(candidate: CandidateManifest): Promise<VerificationStatus>
  commitCandidate(attestation: ScopeAttestation, scopeId?: string): Promise<VerificationStatus>
  reopenScope(scopeId: string): Promise<VerificationStatus>
  status(scopeId?: string): Promise<VerificationStatus>
  close(): Promise<VerificationStatus>
  dispose(): Promise<void>
}

const sha256 = (value: string) => createHash("sha256").update(value, "utf8").digest("hex")

export const goalSource = (
  text: string,
  sourceId = "user-request",
  sourceType: GoalSource["sourceType"] = "user_message",
): GoalSource => ({ sourceId, sourceType, text })

export const sourceReference = (source: GoalSource): SourceReference => ({
  sourceId: source.sourceId,
  sourceType: source.sourceType,
  sha256: sha256(source.text),
})

export const defaultApplicability = (): Applicability => ({
  os: process.platform,
  arch: process.arch,
  runtime: "bun-" + Bun.version,
  provider: "unknown",
  model: "unknown",
  tools: {},
  dependencyLockHash: "unknown",
  configHash: "unknown",
  workspaceRevision: "unknown",
})

export function createGoalContract(
  source: GoalSource,
  options: {
    risk?: Risk
    verifierIds?: string[]
    revision?: number
    constraints?: string[]
  } = {},
): GoalContract {
  const digest = sha256(source.sourceId + "\u0000" + source.text)
  const criterionId = "criterion-" + digest.slice(0, 16)
  const claimId = "claim-" + digest.slice(16, 32)
  const ref = sourceReference(source)
  return {
    schemaVersion: "goal-contract-v2",
    contractId: "contract-" + digest,
    revision: options.revision ?? 1,
    goal: source.text,
    sourceRefs: [ref],
    criteria: [
      {
        criterionId,
        statement: source.text,
        sourceRefs: [ref],
        claimIds: [claimId],
        required: true,
        risk: options.risk ?? "medium",
      },
    ],
    claims: [
      {
        claimId,
        criterionIds: [criterionId],
        origin: "user",
        statement: source.text,
        kind: "execution",
        scope: {
          targets: ["workspace"],
          capabilities: ["requested_execution"],
          exclusions: [],
        },
        applicability: defaultApplicability(),
        predicate: { type: "command_exit", expectedExitCode: 0 },
        verifierPolicy: {
          minimumStrength: "execution",
          allowedVerifierIds: options.verifierIds ?? ["auto"],
          minIndependentFamilies: 1,
        },
      },
    ],
    constraints: options.constraints ?? ["Only verifier-attested evidence may issue Ready."],
  }
}

export function materializeProposal(source: GoalSource, proposal: GoalContractProposal): GoalContract {
  const ref = sourceReference(source)
  const digest = sha256(source.sourceId + "\u0000" + JSON.stringify(proposal))
  return {
    schemaVersion: "goal-contract-v2",
    contractId: "contract-" + digest,
    revision: 1,
    goal: proposal.goal,
    sourceRefs: [ref],
    criteria: proposal.criteria.map((criterion) => ({
      ...criterion,
      sourceRefs: [ref],
    })),
    claims: proposal.claims.map((claim) => ({
      ...claim,
      applicability: {
        ...defaultApplicability(),
        ...claim.applicability,
        tools: claim.applicability?.tools ?? {},
      },
    })),
    constraints: proposal.constraints ?? [],
  }
}
