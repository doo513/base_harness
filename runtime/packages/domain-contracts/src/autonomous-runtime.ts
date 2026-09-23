/// <reference lib="dom" />

import type {
  ActionGate, AuthorityGrant, BudgetLimits, CandidateIntegrityReceipt, CandidateState, CheckSpec, CompletionRecord, DecisionAction, DecisionBasis,
  DecisionProposal, IntentRecord, Json, ObservationReport, Operation, ResourceScope, RunBinding, RunLifecycle,
  SubjectRef, WorkingInterpretation, WorkingInterpretationProposal, AutonomousPreparationResult,
  TaskProposal, TaskState, DomainAssessment, GateResult,
} from "./autonomous"

export interface AutonomousResourceUsage {
  modelTokens: number
  costMinorUnits: number
  /** False means the numeric fields are only the known lower bound. */
  complete?: boolean
}
export interface AutonomousActionEffect { operation: Operation; targets: ResourceScope[] }
export interface AutonomousGateEvidence { subject: SubjectRef; environmentHash: string; notBefore?: string }
export interface AutonomousCandidateFile {
  path: string
  beforeHash: string | null
  afterHash: string | null
}
export interface AutonomousCandidateSeal {
  candidate: SubjectRef & { kind: "candidate" }
  taskId: string
  receipt: CandidateIntegrityReceipt
  files: AutonomousCandidateFile[]
}
export interface AutonomousCandidateApplyResult {
  candidate: SubjectRef & { kind: "candidate" }
  state: "applied" | "recovery_required"
  journalPath?: string
  unresolvedEffects: string[]
}
export interface AutonomousCandidateSnapshot extends AutonomousCandidateSeal {
  state: CandidateState
  supersededBy?: SubjectRef & { kind: "candidate" }
  journalPath?: string
}

export interface AutonomousTaskSnapshot {
  taskId: string
  parentTaskId?: string
  clientTaskKey: string
  revision: number
  depth: number
  state: TaskState
  objective: string
  requestedCapabilities: Operation[]
  requestedScopes: ResourceScope[]
  dependsOn: TaskProposal["dependsOn"]
  sessionId?: string
  output?: Json
  assessment?: DomainAssessment
  report?: SubjectRef & { kind: "report" }
  candidateIds: string[]
  error?: string
}

export interface AutonomousTaskExecutionInput {
  taskId: string
  parentTaskId: string
  proposal: TaskProposal
  requestedScopes: ResourceScope[]
  signal: AbortSignal
}

export interface AutonomousTaskExecutionResult {
  sessionId?: string
  output: Json
}

/** Host-issued revision after the existing question service returns a user reply. */
export interface AutonomousClarification {
  basedOn: DecisionBasis
  questionRevision: number
  intent: IntentRecord
  interpretation: WorkingInterpretation
}

/** Host-authenticated user input appended to an active Run. */
export interface AutonomousIntentRevision {
  basedOn: DecisionBasis
  intent: IntentRecord
  interpretation: WorkingInterpretation
}

export interface AutonomousRunSetup {
  binding: RunBinding
  taskId: string
  intent: IntentRecord
  interpretation: WorkingInterpretation
  authority: AuthorityGrant
  limits: BudgetLimits
  metering: { tokens: boolean; cost: boolean }
  cleanupTimeoutMs: number
  checks: CheckSpec[]
  gates: ActionGate[]
  subjects: SubjectRef[]
  gateEvidence: Record<string, AutonomousGateEvidence>
}

/** Trusted composition ports. Neither these callbacks nor their receipts come from actor JSON. */
export interface AutonomousRunPorts {
  resolveEffects(action: DecisionAction): Promise<AutonomousActionEffect[]>
  /** Workspace-owned hooks. They are called only around admitted mutation/publication effects. */
  beginMutation?(proposal: DecisionProposal, signal: AbortSignal): Promise<void>
  invoke(proposal: DecisionProposal, signal: AbortSignal): Promise<Json>
  sealCandidate?(proposal: DecisionProposal, signal: AbortSignal): Promise<AutonomousCandidateSeal | undefined>
  applyCandidate?(proposal: DecisionProposal, receipt: CandidateIntegrityReceipt, signal: AbortSignal): Promise<AutonomousCandidateApplyResult>
  measure(proposal: DecisionProposal, signal: AbortSignal): Promise<ObservationReport>
  authenticates(report: ObservationReport): boolean
  revise(proposal: WorkingInterpretationProposal): WorkingInterpretation
  /** Trusted Host permission refresh. Actor decisions cannot call this port. */
  reviseAuthority?(authority: AuthorityGrant): Promise<void>
  executeTask?(input: AutonomousTaskExecutionInput): Promise<AutonomousTaskExecutionResult>
  cleanup(): Promise<string[]>
}

export type AutonomousDecisionResult =
  | { accepted: false; code: string }
  | { accepted: true; decisionId: string; output?: Json; observation?: ObservationReport; completion?: CompletionRecord }

export interface AutonomousRunSnapshot {
  semantics: "autonomous-v1"
  lifecycle: RunLifecycle
  binding: RunBinding
  intent: IntentRecord
  interpretation: WorkingInterpretation
  authority: AuthorityGrant
  /** Candidate context from the last Domain Prepare, tied to its exact basis. */
  preparation?: { basis: DecisionBasis; context: Json }
  observations: ObservationReport[]
  candidates: AutonomousCandidateSnapshot[]
  tasks: AutonomousTaskSnapshot[]
  graphRevision: number
  questions: string[]
  questionRevision: number
  completion?: CompletionRecord
  pendingDecisionIds: string[]
  lateResultIds: string[]
  budget: {
    budgetId: string
    limits: BudgetLimits
    actions: number
    used: AutonomousResourceUsage
    reserved: AutonomousResourceUsage
    faulted: boolean
    pending: string[]
    incompleteSettlementIds: string[]
  }
}

/** Stable product projection shared by CLI, HTTP and TUI. It preserves the
 * three independent meanings instead of reducing them to legacy Ready. */
export interface AutonomousProductResult {
  schemaVersion: "autonomous-product-result-v1"
  lifecycle: RunLifecycle
  runtimeReason: CompletionRecord["reason"] | null
  assessment: CompletionRecord["assessment"]
  observations: ObservationReport[]
  gates: GateResult[]
  candidates: Array<{
    candidate: SubjectRef & { kind: "candidate" }
    taskId: string
    state: CandidateState
  }>
  unresolvedEffects: string[]
}

/** Host consumes this port without importing Coordinator implementations. */
export interface AutonomousCoordinatorPort {
  autonomousBasis(sessionID: string, runId: string): DecisionBasis
  prepareAutonomous(sessionID: string, runId: string, preparation: AutonomousPreparationResult): Promise<unknown>
  resumeAutonomous(sessionID: string, runId: string, clarification: AutonomousClarification): Promise<unknown>
  reviseAutonomousIntent(sessionID: string, runId: string, revision: AutonomousIntentRevision): Promise<unknown>
  reviseAutonomousAuthority(sessionID: string, runId: string, authority: AuthorityGrant): Promise<unknown>
  submitAutonomousDecision(sessionID: string, runId: string, proposal: unknown): Promise<AutonomousDecisionResult>
  reserveAutonomousModel(sessionID: string, runId: string, requestId: string, payload: Json, upperBound: AutonomousResourceUsage): Promise<{
    reservation: "reserved" | "replay"; signal?: AbortSignal
  }>
  settleAutonomousModel(sessionID: string, runId: string, requestId: string, usage: AutonomousResourceUsage): Promise<void>
  registerAutonomousSubject(sessionID: string, runId: string, subject: SubjectRef): void
  registerAutonomousCheck(sessionID: string, runId: string, check: CheckSpec): void
}
