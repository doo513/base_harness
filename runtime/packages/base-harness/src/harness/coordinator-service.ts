import { Coordinator as RuntimeCoordinator } from "@base-harness/coordinator"
import { KernelHost, type MetaReviewRequest } from "@base-harness/kernel-host"

const kernel = new KernelHost(RuntimeCoordinator, {
  sessionState: true,
  redact: (runId, value) => RuntimeCoordinator.redactForPersistence(runId, value),
})
RuntimeCoordinator.registerCompletionGate((sessionID) => kernel.canVerifyRoot(sessionID))
RuntimeCoordinator.registerStatusCheckpoint((status) => kernel.checkpointStatus(status))

// Mutating API methods return the same current Host view as GET and status events.
// Only the runtime performs the action; this boundary adds Kernel presentation state.
const runtimeStatus = async (operation: Promise<{ sessionID: string }>) => {
  const completed = await operation
  return kernel.status(completed.sessionID)
}

export const Coordinator = new Proxy(RuntimeCoordinator, {
  get(target, property, receiver) {
    if (property === "openRun" || property === "beginRun") return kernel.openRun.bind(kernel)
    if (property === "submitWorkGraph") return (input: { sessionID: string; graph: unknown; context?: unknown }) =>
      kernel.acceptWorkGraph(input.sessionID, input.graph, input.context)
    if (property === "subscribe") return (listener: (status: any) => void) => {
      const offRuntime = RuntimeCoordinator.subscribe((status) => listener(kernel.status(status.sessionID)))
      const offKernel = kernel.subscribe(listener)
      return () => { offRuntime(); offKernel() }
    }
    if (property === "proposeContract") return kernel.proposeContract.bind(kernel)
    if (property === "acceptWorkGraph") return kernel.acceptWorkGraph.bind(kernel)
    if (property === "status") return kernel.status.bind(kernel)
    if (property === "readStatus") return kernel.readStatus.bind(kernel)
    if (property === "verifyRoot") return (...args: Parameters<typeof target.verifyRoot>) =>
      runtimeStatus(target.verifyRoot(...args))
    if (property === "verify") return (...args: Parameters<typeof target.verify>) =>
      runtimeStatus(target.verify(...args))
    if (property === "cancel") return (...args: Parameters<typeof target.cancel>) =>
      runtimeStatus(target.cancel(...args))
    if (property === "resolvePlan") return kernel.resolvePlan.bind(kernel)
    if (property === "preparePlanExecution") return kernel.preparePlanExecution.bind(kernel)
    if (property === "control") return kernel.control.bind(kernel)
    if (property === "assertToolAllowed") return kernel.assertToolAllowed.bind(kernel)
    if (property === "registerMetaReviewer") return kernel.registerMetaReviewer.bind(kernel)
    if (property === "revalidateContract") return kernel.revalidateContract.bind(kernel)
    const value = Reflect.get(target, property, receiver)
    return typeof value === "function" ? value.bind(target) : value
  },
}) as typeof RuntimeCoordinator & {
  openRun(input: any): Promise<any>
  proposeContract(sessionID: string, proposal: unknown, context?: unknown): Promise<any>
  acceptWorkGraph(sessionID: string, graph: unknown, context?: unknown): Promise<any>
  readStatus: KernelHost["readStatus"]
  resolvePlan: KernelHost["resolvePlan"]
  preparePlanExecution: KernelHost["preparePlanExecution"]
  control: KernelHost["control"]
  assertToolAllowed(
    sessionID: string, toolID: string, subagentType?: string,
    hostOperation?: import("@base-harness/kernel").ToolOperation,
  ): void
  registerMetaReviewer(reviewer: (request: MetaReviewRequest) => Promise<unknown>): void
  revalidateContract(
    sessionID: string,
    trigger: import("@base-harness/kernel").ContractRevalidationTrigger,
    affectedClaimIds?: string[],
    affectedCriterionIds?: string[],
  ): unknown
}
export const Orchestration = RuntimeCoordinator.orchestration
export type {
  ContractPreflightResult,
  ContractRevalidationTrigger,
  HarnessControl,
  InterpretationProposal,
  KernelSessionState,
  PlanSpec,
} from "@base-harness/kernel"
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
