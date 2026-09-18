/// <reference lib="dom" />

import type {
  ActionGate, AuthorityGrant, BudgetLimits, CheckSpec, CompletionRecord, DecisionAction, DecisionBasis,
  DecisionProposal, IntentRecord, Json, ObservationReport, Operation, ResourceScope, RunBinding, RunLifecycle,
  SubjectRef, WorkingInterpretation, WorkingInterpretationProposal, AutonomousPreparationResult,
} from "./autonomous"

export interface AutonomousResourceUsage {
  modelTokens: number
  costMinorUnits: number
  /** False means the numeric fields are only the known lower bound. */
  complete?: boolean
}
export interface AutonomousActionEffect { operation: Operation; targets: ResourceScope[] }
export interface AutonomousGateEvidence { subject: SubjectRef; environmentHash: string; notBefore?: string }

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
  invoke(proposal: DecisionProposal, signal: AbortSignal): Promise<Json>
  measure(proposal: DecisionProposal, signal: AbortSignal): Promise<ObservationReport>
  authenticates(report: ObservationReport): boolean
  revise(proposal: WorkingInterpretationProposal): WorkingInterpretation
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

/** Host consumes this port without importing Coordinator implementations. */
export interface AutonomousCoordinatorPort {
  autonomousBasis(sessionID: string, runId: string): DecisionBasis
  prepareAutonomous(sessionID: string, runId: string, preparation: AutonomousPreparationResult): Promise<unknown>
  resumeAutonomous(sessionID: string, runId: string, clarification: AutonomousClarification): Promise<unknown>
  reviseAutonomousIntent(sessionID: string, runId: string, revision: AutonomousIntentRevision): Promise<unknown>
  submitAutonomousDecision(sessionID: string, runId: string, proposal: unknown): Promise<AutonomousDecisionResult>
  reserveAutonomousModel(sessionID: string, runId: string, requestId: string, payload: Json, upperBound: AutonomousResourceUsage): Promise<{
    reservation: "reserved" | "replay"; signal?: AbortSignal
  }>
  settleAutonomousModel(sessionID: string, runId: string, requestId: string, usage: AutonomousResourceUsage): Promise<void>
  registerAutonomousSubject(sessionID: string, runId: string, subject: SubjectRef): void
  registerAutonomousCheck(sessionID: string, runId: string, check: CheckSpec): void
}
