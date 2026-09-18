import type { ContractBody } from "./goal-contract"

import type {
  DomainId,
  DomainOperation,
  OverlayId,
  DomainPolicySnapshot,
  DomainSelection,
  ReadonlyValue,
  SkillRef,
} from "./domain"

export interface WorkUnit {
  id: string
  title: string
  instructions: string
  agentType?: string
  claimIds: string[]
  criterionIds: string[]
  dependsOn: string[]
  readSet: string[]
  writeSet: string[]
  integrationRequests: string[]
}

export interface WorkGraph {
  units: WorkUnit[]
  integrationPaths: string[]
}

export type DomainExecutorKind = "model_api" | "agent_runtime"

/** Trusted application selection. It identifies an adapter; it does not execute it. */
export interface DomainExecutorSelection {
  id: string
  revision: string
  kind: DomainExecutorKind
  connectionId?: string
  providerId?: string
  modelId?: string
  options: Record<string, string>
}

export interface StrategyIdentity {
  id: string
  revision: string
}

/** Exact metadata and executable strategies selected for one policy overlay. */
export interface DomainExecutionOverlayBinding {
  overlayId: OverlayId
  overlayRevision: string
  module: StrategyIdentity
  preparationStrategy: StrategyIdentity
  proposalStrategy: StrategyIdentity
}

/** Run-independent selection fixed by the Host immediately before a run is opened. */
export interface DomainExecutionBinding {
  schemaVersion: "domain-execution-binding-v1"
  selection: DomainSelection
  policy: DomainPolicySnapshot
  module: StrategyIdentity
  preparationStrategy: StrategyIdentity
  proposalStrategy: StrategyIdentity
  overlays: DomainExecutionOverlayBinding[]
  executor: DomainExecutorSelection
}

/** Serializable identity of the strategies and executor pinned to one Coordinator run. */
export interface DomainRunBinding extends DomainExecutionBinding {
  runId: string
}

export interface DomainPreparationInput {
  sessionID: string
  workspace: string
  goal: string
  selection: ReadonlyValue<DomainSelection>
  policy: ReadonlyValue<DomainPolicySnapshot>
  skills: readonly ReadonlyValue<SkillRef>[]
  executor: ReadonlyValue<DomainExecutorSelection>
  environment: Readonly<Record<string, string>>
}

/** Candidate context only. It carries neither contract acceptance nor verification state. */
export interface DomainPreparation {
  schemaVersion: "domain-preparation-v1"
  domainId: DomainId
  mode: "read" | "develop"
  goal: string
  workspace: string
  instructions: string[]
  allowedOperations: DomainOperation[]
  allowedSubagentTypes: string[]
  overlays: Array<{ id: OverlayId; revision: string }>
  /** Selected knowledge references. Older/injected preparations may omit an empty set. */
  skills?: SkillRef[]
  environment: Record<string, string>
}

export interface DirectExecutionProposal {
  kind: "direct"
  /** Attached means the already-running Host model loop; adapter requests a registered executor. */
  dispatch: "attached" | "adapter"
  instruction: string
  mutationPolicy: "forbid" | "capture"
}

export interface WorkGraphExecutionProposal {
  kind: "work_graph"
  graph: WorkGraph
}

export type DomainExecutionProposal = DirectExecutionProposal | WorkGraphExecutionProposal

export interface DomainProposalInput {
  sessionID: string
  runId: string
  proposal: unknown
  preparation: ReadonlyValue<DomainPreparation>
  binding: ReadonlyValue<DomainRunBinding>
  contract: ReadonlyValue<ContractBody>
}

export interface DomainPreparationStrategy {
  readonly id: string
  readonly revision: string
  prepare(input: ReadonlyValue<DomainPreparationInput>): DomainPreparation
}

export interface DomainProposalStrategy {
  readonly id: string
  readonly revision: string
  normalize(input: ReadonlyValue<DomainProposalInput>): DomainExecutionProposal
}

export interface DomainOverlayPreparationInput extends DomainPreparationInput {
  overlayId: OverlayId
  overlayRevision: string
  preparation: ReadonlyValue<DomainPreparation>
}

export interface DomainOverlayProposalInput extends Omit<DomainProposalInput, "proposal"> {
  overlayId: OverlayId
  overlayRevision: string
  proposal: ReadonlyValue<DomainExecutionProposal>
}

export interface DomainOverlayPreparationStrategy {
  readonly id: string
  readonly revision: string
  apply(input: ReadonlyValue<DomainOverlayPreparationInput>): DomainPreparation
}

export interface DomainOverlayProposalStrategy {
  readonly id: string
  readonly revision: string
  apply(input: ReadonlyValue<DomainOverlayProposalInput>): DomainExecutionProposal
}

/** Domain behavior registered separately from metadata resolution. */
export interface DomainExecutionModule {
  readonly id: string
  readonly revision: string
  readonly domainId: DomainId
  readonly preparation: DomainPreparationStrategy
  readonly proposal: DomainProposalStrategy
}

/** Executable behavior for a metadata overlay; it composes around a Domain module. */
export interface DomainExecutionOverlayModule {
  readonly id: string
  readonly revision: string
  readonly overlayId: OverlayId
  readonly compatibleDomains: readonly DomainId[]
  readonly preparation: DomainOverlayPreparationStrategy
  readonly proposal: DomainOverlayProposalStrategy
}

export interface DomainExecutionModuleResolver {
  resolve(domainId: DomainId): DomainExecutionModule
  resolveOverlay(overlayId: OverlayId): DomainExecutionOverlayModule
}

/** Minimal cancellation surface so this dependency-free package does not require DOM library types. */
export interface DomainExecutionSignal {
  readonly aborted: boolean
  readonly reason?: unknown
  throwIfAborted(): void
  addEventListener(type: "abort", listener: () => void, options?: { once?: boolean }): void
  removeEventListener(type: "abort", listener: () => void): void
}

export interface DomainExecutionDispatchRequest {
  sessionID: string
  runId: string
  workspace: string
  goal: string
  signal: DomainExecutionSignal
  binding: ReadonlyValue<DomainRunBinding>
  preparation: ReadonlyValue<DomainPreparation>
  proposal: ReadonlyValue<DirectExecutionProposal>
  /** Opaque Host capability. It is never part of a persisted binding or preparation. */
  context: unknown
}

/** Untrusted execution output retained as candidate data until the verifier observes real evidence. */
export interface DomainExecutionResult {
  runId: string
  output: string
  changedFiles: string[]
  adapterId: string
  modelId?: string
}

export type DomainExecutionDispatcher = (
  request: DomainExecutionDispatchRequest,
) => Promise<DomainExecutionResult>

export type DomainExecutionErrorCode =
  | "DOMAIN_EXECUTION_MODULE_INVALID"
  | "DOMAIN_EXECUTION_MODULE_DUPLICATE"
  | "DOMAIN_EXECUTION_MODULE_UNREGISTERED"
  | "DOMAIN_EXECUTION_OVERLAY_INVALID"
  | "DOMAIN_EXECUTION_OVERLAY_DUPLICATE"
  | "DOMAIN_EXECUTION_OVERLAY_UNREGISTERED"
  | "DOMAIN_EXECUTION_OVERLAY_INCOMPATIBLE"
  | "DOMAIN_PREPARATION_INVALID"
  | "DOMAIN_PROPOSAL_INVALID"
  | "DOMAIN_PROPOSAL_FORBIDDEN"
  | "DOMAIN_PROPOSAL_BINDING_INVALID"
  | "DOMAIN_RUN_BINDING_INVALID"
  | "DOMAIN_RUN_MISMATCH"
