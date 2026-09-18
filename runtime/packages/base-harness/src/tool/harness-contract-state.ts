import { Coordinator } from "../harness/coordinator-service"
import type * as Tool from "./tool"
import { operationForTool, type ToolOperation } from "@base-harness/kernel"
import type { ContractSubmission as HarnessContractProposal } from "@base-harness/domain-contracts"
export type { ContractSubmission as HarnessContractProposal } from "@base-harness/domain-contracts"

/** Historical name retained for callers. Submission history has no admission authority. */
export function assertHarnessContractSubmitted(sessionID: string, toolID: string, hostOperation?: ToolOperation, subagentType?: string) {
  Coordinator.assertToolAllowed(sessionID, toolID, subagentType, hostOperation)
  // The new path has already checked a Run-owned invocation lease and grant.
  // Do not impose a second, legacy GoalContract authority on that same action.
  if (Coordinator.status(sessionID).autonomous) return
  const operation = hostOperation ?? operationForTool(toolID)
  const requiresContract = operation === "mutate" || operation === "execute"
    || (operation === "delegate" && subagentType !== "explore" && subagentType !== "meta-review")
  if (requiresContract && !Coordinator.hasAcceptedContract(sessionID)) {
    throw new Error("CONTRACT_REQUIRED: submit a GoalContract before state-changing tools")
  }
}

export async function registerHarnessContractProposal(sessionID: string, params: HarnessContractProposal, context?: Tool.Context) {
  return Coordinator.proposeContract(sessionID, params, context)
}
