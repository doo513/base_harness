import type * as Orchestration from "@base-harness/core/orchestration"
import type {
  GoalContractProposal,
  VerificationProfile,
  VerificationStatus,
} from "@base-harness/verification"

export type WorkerState =
  | "queued"
  | "running"
  | "candidate_ready"
  | "verifying"
  | "committing"
  | "repairing"
  | "completed"
  | "failed"
  | "repair_exhausted"

export interface CoordinatorWorkerStatus {
  workUnitId: string
  title: string
  state: WorkerState
  scopeId?: string
  repairCount: number
  failureFingerprint?: string
}

export interface HarnessStatus {
  sessionID: string
  workspace: string
  runId: string
  goal: string
  phase: Orchestration.Phase | "inactive"
  workers: CoordinatorWorkerStatus[]
  activeCount: number
  queuedCount: number
  outcome?: VerificationStatus["outcome"]
  verificationState: VerificationStatus["state"]
  configuredProfile?: VerificationProfile
  effectiveProfile?: VerificationProfile
  assuranceLevel?: VerificationProfile
  failureKind?: string | null
  failedCriterion?: string | null
  missingEvidence: string[]
  repairCount: number
  maxSameFailureRepairs: number
  evidenceCount: number
  candidateCount: number
  readyEligible: boolean
  message?: string
  metrics: {
    observedActions: number
    workers: number
    activeWorkers: number
    repairs: number
    evidence: number
    sandboxRuns: number
  }
  isolation?: IsolationStatus
}

export interface IsolationStatus {
  backend: "wsl2" | "namespace" | "native"
  containment: string
  network: "loopback_only" | "host"
  state: "running" | "completed" | "failed"
  code?: string
  distro?: string
  kernel?: string
  timeoutMs?: number
  memoryMiB?: number
  maxProcesses?: number
  maxOutputBytes?: number
  inputBytes?: number
}

export interface BeginRunInput {
  sessionID: string
  workspace: string
  goal: string
  configuredProfile?: VerificationProfile
  effectiveProfile?: VerificationProfile
  maxSameFailureRepairs?: number
  maxParallelWorkUnits?: number
  trigger?: "auto" | "manual"
  context?: unknown
}

export interface HostActionEvent {
  type: string
  data: unknown
}

export interface VerificationTarget {
  sessionID: string
  reason?: "automatic" | "manual" | "completion"
}

export interface WorkerExecutionRequest {
  rootSessionID: string
  unit: Orchestration.WorkUnit
  context: unknown
  taskID?: string
  repairPrompt?: string
}

export interface WorkerExecutionResult {
  sessionID: string
  output?: string
}

export type WorkerExecutor = (request: WorkerExecutionRequest) => Promise<WorkerExecutionResult>

export interface IntegrationExecutionRequest {
  rootSessionID: string
  context: unknown
  integrationPaths: string[]
  integrationRequests: string[]
  repairPrompt?: string
}

export type IntegrationExecutor = (request: IntegrationExecutionRequest) => Promise<void>
export type StatusPublisher = (status: HarnessStatus) => void | Promise<void>

export interface CoordinatorService {
  beginRun(input: BeginRunInput): Promise<HarnessStatus>
  observe(event: HostActionEvent): Promise<void>
  submitWorkGraph(input: {
    sessionID: string
    graph: Orchestration.WorkGraph
    context: unknown
  }): Promise<HarnessStatus>
  verify(target: VerificationTarget): Promise<HarnessStatus>
  cancel(sessionID: string): Promise<HarnessStatus>
  status(sessionID: string): HarnessStatus
}

export type { GoalContractProposal, VerificationProfile, VerificationStatus }
export type { WorkGraph, WorkUnit } from "@base-harness/core/orchestration"
