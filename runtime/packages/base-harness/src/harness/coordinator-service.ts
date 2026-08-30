import { Coordinator as RuntimeCoordinator } from "@base-harness/coordinator"

export const Coordinator = RuntimeCoordinator
export const Orchestration = RuntimeCoordinator.orchestration

export type {
  CoordinatorService,
  GoalContractProposal,
  HarnessStatus,
  HostActionEvent,
  VerificationStatus,
  VerificationTarget,
  WorkGraph,
  WorkUnit,
} from "@base-harness/coordinator"
