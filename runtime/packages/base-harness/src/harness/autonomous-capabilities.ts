import type { Operation } from "@base-harness/domain-contracts"

const nativeToolOperations = new Map<string, Operation>([
  ["read", "read"],
  ["glob", "search"],
  ["grep", "search"],
  ["bash", "execute"],
])

/** Code-owned capability catalog. Callers cannot mutate the backing map. */
export function isAutonomousNativeTool(toolId: string): boolean {
  return nativeToolOperations.has(toolId)
}

export function autonomousNativeToolOperation(toolId: string): Operation | undefined {
  return nativeToolOperations.get(toolId)
}
