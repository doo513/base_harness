import { expect, test } from "bun:test"
import { KernelHost } from "@base-harness/kernel-host"
import { operationForMcpTool } from "../../src/harness/mcp-operation"

test("MCP operation classification uses typed catalog hints and fails closed for missing or conflicting hints", () => {
  expect(operationForMcpTool({ annotations: { readOnlyHint: true, destructiveHint: false } })).toBe("read")
  expect(operationForMcpTool({ annotations: { readOnlyHint: false, destructiveHint: false } })).toBe("execute")
  for (const descriptor of [{}, { annotations: { readOnlyHint: true } }, { annotations: { readOnlyHint: true, destructiveHint: true } }]) {
    expect(operationForMcpTool(descriptor)).toBe("unknown")
  }
  expect(operationForMcpTool({ description: "read-only safe search" } as {})).toBe("unknown")
})

test("planning allows a catalog-classified read but rejects MCP writes and unclassified tools", async () => {
  const host = new KernelHost({
    openRun: async () => ({ sessionID: "root", runId: "run" }),
    status: () => ({ sessionID: "root", runId: "run" }),
    proposeContract: async () => ({}),
    acceptWorkGraph: async () => ({}),
  })
  await host.openRun({ sessionID: "root", workspace: "workspace", goal: "Plan only" })
  expect(() => host.assertToolAllowed("root", "fixture_echo", undefined, "read")).not.toThrow()
  expect(() => host.assertToolAllowed("root", "fixture_write", undefined, "execute")).toThrow("PLAN_ONLY_MUTATION_DENIED")
  expect(() => host.assertToolAllowed("root", "fixture_echo")).toThrow("PLAN_ONLY_MUTATION_DENIED")
})
