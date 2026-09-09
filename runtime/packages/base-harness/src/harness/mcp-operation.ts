import type { ToolOperation } from "@base-harness/kernel"
import { Orchestration } from "./coordinator-service"
import { assertHarnessContractSubmitted } from "../tool/harness-contract-state"

interface McpDescriptor {
  annotations?: {
    readOnlyHint?: boolean
    destructiveHint?: boolean
  }
}

/** Descriptor comes from the configured MCP catalog, not Actor arguments or prose. */
export function operationForMcpTool(descriptor: McpDescriptor): ToolOperation {
  const annotations = descriptor.annotations
  if (annotations?.readOnlyHint === true && annotations.destructiveHint === false) return "read"
  if (annotations?.readOnlyHint === false) return "execute"
  return "unknown"
}

export function assertMcpOperationAllowed(sessionID: string, toolID: string, operation: ToolOperation) {
  const owner = Orchestration.snapshot(sessionID)
  // An MCP hint must never grant worker, explore or reviewer capabilities.
  if (owner && owner.sessionID !== sessionID) {
    throw Object.assign(new Error("MCP_SCOPE_PERMISSION_DENIED"), { code: "MCP_SCOPE_PERMISSION_DENIED" })
  }
  assertHarnessContractSubmitted(sessionID, toolID, operation)
  Orchestration.assertToolAllowed(sessionID, operation === "read" ? "read" : toolID)
}
