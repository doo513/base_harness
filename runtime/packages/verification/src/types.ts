export const SIDECAR_PROTOCOL_VERSION = 1 as const

export type VerificationOutcome = "ready" | "repair" | "blocked" | "failure"
export type VerificationState = "inactive" | "starting" | "open" | "observing" | VerificationOutcome | "closed"

export interface GoalContract {
  goal: string
  acceptance: string[]
  constraints?: string[]
  metadata?: Record<string, unknown>
}

export interface ArtifactReference {
  artifactType: string
  sha256: string
  path: string
  trust: "untrusted_execution_observation" | "verifier_observed" | "verifier_attested"
}

export interface VerificationStatus {
  state: VerificationState
  goal: string
  runId: string
  scopeId: string
  rootScopeId: string
  outcome?: VerificationOutcome
  failureKind?: string | null
  failedCriterion?: string | null
  missingEvidence?: string[]
  repairScope?: string | null
  repairCount?: number
  failureFingerprint?: string
  message?: string
  evidenceRefs: ArtifactReference[]
  candidateRefs: ArtifactReference[]
  readyRef?: ArtifactReference | null
  maxSameFailureRepairs: number
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
  goalContract: GoalContract
}

export interface ObserveActionInput {
  scopeId?: string
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
  openScope(scopeId: string, parentScopeId: string): Promise<VerificationStatus>
  observe(input: ObserveActionInput): Promise<VerificationStatus>
  verify(reason: "automatic" | "manual" | "completion", scopeId?: string): Promise<VerificationStatus>
  status(scopeId?: string): Promise<VerificationStatus>
  close(): Promise<VerificationStatus>
  dispose(): Promise<void>
}
