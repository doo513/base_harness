/**
 * Design-only contract model. Not imported by the runtime and not a security
 * implementation. The normative behavior is in the linked design document.
 * Host authentication, digest checks and admission must exist at runtime;
 * receiving an object of one of these types grants no authority.
 */

export type Json = null | boolean | number | string | Json[] | { [key: string]: Json }

export interface VersionRef {
  id: string
  revision: number
  sha256: string
}

export interface SourceRef {
  sourceId: string
  sha256: string
}

/** Digest of the complete immutable subject manifest, including relevant inputs. */
export interface SubjectRef extends VersionRef {
  kind: "source" | "report" | "candidate" | "workspace" | "resource_snapshot"
}

export interface UserRequirement {
  id: string
  text: string
  sourceRefs: SourceRef[]
}

/** Host-owned transcription with provenance; model interpretations are separate. */
export interface IntentRecord {
  schemaVersion: "intent-v1"
  ref: VersionRef
  originalRequest: SubjectRef
  requirements: UserRequirement[]
  constraints: UserRequirement[]
}

/** An evolving working explanation, not an executable permission grant. */
export interface WorkingInterpretation {
  schemaVersion: "interpretation-v1"
  ref: VersionRef
  intentRef: VersionRef
  goalSummary: string
  assumptions: Array<{ id: string; statement: string; observationIds: string[] }>
  openQuestions: string[]
  proposedCheckIds: string[]
}

/** The Host allocates the next record reference after checking the prior revision. */
export type WorkingInterpretationProposal = Omit<WorkingInterpretation, "ref"> & {
  basedOnRef: VersionRef
}

export type Operation = "read" | "search" | "mutate" | "execute" | "delegate" | "publish"

export interface ResourceScope {
  kind: "workspace_path" | "network_origin" | "external_resource"
  selector: string
}

export interface AuthorityGrant {
  schemaVersion: "authority-v1"
  ref: VersionRef
  runId: string
  parentRef?: VersionRef
  provenanceRefs: SourceRef[]
  capabilities: Array<{
    operation: Operation
    targets: ResourceScope[]
    exclusions: ResourceScope[]
  }>
  expiresAt: string
}

/** Runtime meters and atomically reserves these resources across all children. */
export interface BudgetLimits {
  deadlineAt: string
  maxActions: number
  maxParallelTasks: number
  maxTaskDepth: number
  maxTotalTasks: number
  maxModelTokens?: number
  maxCost?: { currency: string; minorUnits: number }
}

/** No new ledger or deadline is created merely by revising an interpretation. */
export interface RunBinding {
  schemaVersion: "autonomous-run-binding-v1"
  runId: string
  semantics: "autonomous-v1"
  domainModule: VersionRef
  executor: VersionRef
  authorityRef: VersionRef
  budgetId: string
}

/** Registered by the Host; an ad-hoc model-authored check remains identified as such. */
export interface CheckSpec {
  schemaVersion: "check-spec-v1"
  ref: VersionRef
  author: "application" | "user" | "model"
  executorId: string
  supportedSubjects: SubjectRef["kind"][]
  parameters: Json
  requiredCapabilities: Operation[]
  timeoutMs: number
}

export type Finding =
  | { kind: "value"; name: string; observed: Json }
  | {
      kind: "comparison"
      name: string
      operator: "equals" | "contains" | "registered_comparator"
      expected: Json
      observed: Json
      result: "pass" | "fail"
    }

export type MeasurementResult =
  | { execution: "completed"; findings: Finding[] }
  | { execution: "not_run"; reason: string }
  | {
      execution: "error"
      error: { code: string; message: string }
      partialFindings: Finding[]
    }

/** Created through an authenticated measuring adapter, never an actor tool argument. */
export interface ObservationReport {
  schemaVersion: "observation-v1"
  observationId: string
  requestId: string
  runId: string
  taskId: string
  subject: SubjectRef
  checkRef: VersionRef
  environmentHash: string
  startedAt: string
  finishedAt: string
  producer: { kind: "verifier"; id: string; revision: string }
  result: MeasurementResult
  artifacts: SubjectRef[]
  limitations: string[]
}

/** Explicitly bound mechanical gates only; a suggested model check is not a gate. */
export interface ActionGate {
  id: string
  source: "explicit_user" | "trusted_policy"
  sourceRefs: SourceRef[]
  action: "apply_candidate" | "finish_satisfied" | "external_publish"
  checkRef: VersionRef
  requiredComparisons: string[]
}

export interface DecisionBasis {
  runId: string
  taskId: string
  taskRevision: number
  intentRef: VersionRef
  interpretationRef: VersionRef
  authorityRef: VersionRef
}

export interface TaskProposal {
  clientTaskKey: string
  objective: string
  requestedCapabilities: Operation[]
  requestedScopes?: ResourceScope[]
  dependsOn: Array<{
    taskId: string
    when: "settled" | "artifact_produced" | "applied"
  }>
}

export type TaskAmendment =
  | { kind: "add"; task: TaskProposal }
  | { kind: "replace_pending"; taskId: string; task: TaskProposal }
  | { kind: "cancel"; taskId: string }

export interface DomainAssessment {
  status: "satisfied" | "partial" | "unsolved" | "not_assessed"
  summary: string
  citedObservationIds: string[]
  uncertainties: string[]
}

export type DecisionAction =
  | { kind: "invoke"; toolId: string; arguments: Json }
  | { kind: "measure"; checkRef: VersionRef; subject: SubjectRef }
  | { kind: "delegate"; tasks: TaskProposal[] }
  | { kind: "revise_interpretation"; proposal: WorkingInterpretationProposal }
  | { kind: "amend_tasks"; expectedGraphRevision: number; changes: TaskAmendment[] }
  | { kind: "ask"; reason: "information" | "authority"; questions: string[] }
  | { kind: "apply_candidate"; candidate: SubjectRef & { kind: "candidate" } }
  | {
      kind: "finish"
      report: SubjectRef & { kind: "report" }
      assessment: DomainAssessment
      openWork: "drain" | "cancel"
    }

export type FinishProposal = Extract<DecisionAction, { kind: "finish" }>

/** Normal tool calls can be normalized by adapters; not every thought needs a form. */
export interface DecisionProposal {
  schemaVersion: "decision-v1"
  decisionId: string
  basis: DecisionBasis
  observationIds: string[]
  action: DecisionAction
}

export type AdmissionResult =
  | { accepted: true; decisionId: string; permitId: string }
  | { accepted: false; decisionId: string; code: string; affectedIds: string[] }

export type RunLifecycle = "preparing" | "active" | "waiting_input" | "closing" | "closed"
export type TaskState = "pending" | "running" | "waiting_input" | "settled" | "cancelled" | "faulted"
export type TerminationReason =
  | "requested"
  | "cancelled"
  | "budget_exhausted"
  | "deadline_exceeded"
  | "runtime_fault"
  | "interrupted"

export type CandidateState =
  | "editing" | "sealed" | "applying" | "applied" | "retained" | "discarded" | "recovery_required"

/** This is an integrity receipt for bytes, not a certificate of task correctness. */
export interface CandidateIntegrityReceipt {
  receiptId: string
  runId: string
  authorityRef: VersionRef
  candidate: SubjectRef & { kind: "candidate" }
  baselineHash: string
  patchHash: string
}

export interface GateResult {
  gateId: string
  state: "met" | "unmet" | "unknown"
  observationIds: string[]
}

/** Only the runtime closes a run; a model's assessment remains visibly model-authored. */
export interface CompletionRecord {
  schemaVersion: "completion-v1"
  runId: string
  intentRef: VersionRef
  interpretationRef: VersionRef
  reason: TerminationReason
  assessment: DomainAssessment | null
  observationIds: string[]
  gates: GateResult[]
  candidateDispositions: Array<{
    candidate: SubjectRef & { kind: "candidate" }
    state: "applied" | "retained" | "discarded" | "recovery_required"
  }>
  unresolvedEffects: string[]
  endedAt: string
}
