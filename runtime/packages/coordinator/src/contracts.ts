import type * as Orchestration from "@base-harness/workspace/orchestration"
import type { AutonomousRun, AutonomousRunPorts, AutonomousRunSetup } from "./autonomous-run"
import type {
  DomainExecutionBinding,
  DomainExecutionDispatcher,
  DomainExecutionProposal,
  DomainExecutionResult,
  DomainPreparation,
  DomainRunBinding,
} from "@base-harness/domain-contracts"
import type {
  GoalContractProposal,
  DomainPolicySnapshot,
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
  output?: string
}

export interface ExecutionSelection {
  adapterID: string
  modelID?: string
  options?: Record<string, string>
  capabilityRevision?: string
  kind?: "model_api" | "agent_runtime"
  backendId?: string
  connectionId?: string
}

export interface HarnessStatus {
  sessionID: string
  workspace: string
  runId: string
  goal: string
  phase: Orchestration.Phase | "inactive" | "plan_ready" | "autonomous"
  /** Separate semantics; never interpreted through legacy outcome/Ready fields. */
  autonomous?: ReturnType<AutonomousRun["snapshot"]>
  executionPlan?: ExecutionPlanLink
  revisesPlan?: ExecutionPlanLink
  workers: CoordinatorWorkerStatus[]
  activeCount: number
  queuedCount: number
  outcome?: VerificationStatus["outcome"]
  verificationState: VerificationStatus["state"]
  contractStatus?: "missing" | "accepted"
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
  evidenceRefs: string[]
  candidateRefs: string[]
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
  execution?: ExecutionSelection
  domainPolicy?: DomainPolicySnapshot
  domainBinding?: DomainRunBinding
  domainPreparation?: DomainPreparation
  /** Candidate output only; never verifier Evidence or Ready. */
  domainResult?: DomainExecutionResult
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

export interface ExecutionPlanLink {
  planningRunId: string
  planId: string
  planRevision: number
  goalContractHash: string
}

export interface PlanExecutionInput extends ExecutionPlanLink {
  context?: unknown
  execution?: ExecutionSelection
  domainPolicy?: DomainPolicySnapshot
  domainBinding?: DomainExecutionBinding
  domainPreparation?: DomainPreparation
}

export interface RestoredPlanExecutionInput extends PlanExecutionInput, Omit<BeginRunInput, "sessionID"> {
  contract: GoalContractProposal
}

export interface BeginRunInput {
  /** Trusted Host composition only. A JSON actor cannot install executable ports. */
  autonomousFactory?: (runId: string) => Promise<{ setup: AutonomousRunSetup; ports: AutonomousRunPorts }>
  sessionID: string
  workspace: string
  goal: string
  /** Host-owned link to the reviewed plan being revised, never an actor proposal. */
  revisesPlan?: ExecutionPlanLink
  configuredProfile?: VerificationProfile
  effectiveProfile?: VerificationProfile
  maxSameFailureRepairs?: number
  maxParallelWorkUnits?: number
  trigger?: "auto" | "manual"
  execution?: ExecutionSelection
  context?: unknown
  domainPolicy?: DomainPolicySnapshot
  domainBinding?: DomainExecutionBinding
  domainPreparation?: DomainPreparation
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
  /** Owned by the Coordinator run, not a parent model stream or tool call. */
  signal: AbortSignal
  runId: string
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
  signal: AbortSignal
  runId: string
  rootSessionID: string
  context: unknown
  integrationPaths: string[]
  integrationRequests: string[]
  repairPrompt?: string
}

export type IntegrationExecutor = (request: IntegrationExecutionRequest) => Promise<void>
export type StatusPublisher = (status: HarnessStatus) => void | Promise<void>

export interface DomainProposalSubmission {
  sessionID: string
  runId: string
  proposal: DomainExecutionProposal
  context: unknown
}

export interface DomainResultSubmission {
  sessionID: string
  runId: string
  result: Omit<DomainExecutionResult, "runId">
}

export interface CoordinatorService {
  beginRun(input: BeginRunInput): Promise<HarnessStatus>
  observe(event: HostActionEvent): Promise<void>
  submitWorkGraph(input: {
    sessionID: string
    graph: Orchestration.WorkGraph
    context: unknown
  }): Promise<HarnessStatus>
  submitDomainProposal(input: DomainProposalSubmission): Promise<HarnessStatus>
  recordDomainResult(input: DomainResultSubmission): Promise<HarnessStatus>
  verify(target: VerificationTarget): Promise<HarnessStatus>
  cancel(sessionID: string): Promise<HarnessStatus>
  status(sessionID: string): HarnessStatus
}

export type { GoalContractProposal, VerificationProfile, VerificationStatus }
export type { WorkGraph, WorkUnit } from "@base-harness/workspace/orchestration"
export type {
  DomainExecutionBinding,
  DomainExecutionDispatcher,
  DomainExecutionProposal,
  DomainExecutionResult,
  DomainPreparation,
  DomainRunBinding,
}
