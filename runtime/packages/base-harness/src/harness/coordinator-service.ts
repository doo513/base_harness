import { Coordinator as RuntimeCoordinator } from "@base-harness/coordinator"
import { KernelHost, type MetaReviewRequest } from "./kernel-host"

const kernel = new KernelHost(RuntimeCoordinator)

export const Coordinator = new Proxy(RuntimeCoordinator, {
  get(target, property, receiver) {
    if (property === "openRun") return kernel.openRun.bind(kernel)
    if (property === "proposeContract") return kernel.proposeContract.bind(kernel)
    if (property === "acceptWorkGraph") return kernel.acceptWorkGraph.bind(kernel)
    if (property === "status") return kernel.status.bind(kernel)
    if (property === "control") return kernel.control.bind(kernel)
    if (property === "assertToolAllowed") return kernel.assertToolAllowed.bind(kernel)
    if (property === "registerMetaReviewer") return kernel.registerMetaReviewer.bind(kernel)
    const value = Reflect.get(target, property, receiver)
    return typeof value === "function" ? value.bind(target) : value
  },
}) as typeof RuntimeCoordinator & {
  openRun(input: any): Promise<any>
  proposeContract(sessionID: string, proposal: unknown, context?: unknown): Promise<any>
  acceptWorkGraph(sessionID: string, graph: unknown, context?: unknown): Promise<any>
  control(sessionID: string, control: import("@base-harness/kernel").HarnessControl): Promise<unknown>
  assertToolAllowed(sessionID: string, toolID: string, subagentType?: string): void
  registerMetaReviewer(reviewer: (request: MetaReviewRequest) => Promise<unknown>): void
}
export const Orchestration = RuntimeCoordinator.orchestration
export type { HarnessControl, KernelSessionState, PlanSpec } from "@base-harness/kernel"
export type { MetaReviewRequest } from "./kernel-host"

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
