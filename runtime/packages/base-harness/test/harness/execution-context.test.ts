import { expect, test } from "bun:test"
import { Effect } from "effect"
import { captureExecutionContext, executionBridge } from "../../src/harness/execution-context"
import { InstanceRef } from "../../src/effect/instance-ref"
import { InstanceState } from "../../src/effect/instance-state"
import type { InstanceContext } from "../../src/project/instance-context"

async function capture(sessionID: string, directory: string) {
  return Effect.runPromise(captureExecutionContext(sessionID, { extra: { promptOps: {} } }).pipe(
    Effect.provideService(InstanceRef, { directory } as InstanceContext),
  ))
}

test("request capture preserves InstanceRef after returning to an asynchronous coordinator callback", async () => {
  const context = await capture("root", "workspace-a")
  await Promise.resolve()
  const bridge = executionBridge(context, "root", "workspace-a")
  expect(await bridge.promise(InstanceState.directory)).toBe("workspace-a")
})

test("different request workspaces do not share a service initialization context", async () => {
  const [a, b] = await Promise.all([capture("a", "workspace-a"), capture("b", "workspace-b")])
  const values = await Promise.all([
    executionBridge(a, "a", "workspace-a").promise(InstanceState.directory),
    executionBridge(b, "b", "workspace-b").promise(InstanceState.directory),
  ])
  expect(values).toEqual(["workspace-a", "workspace-b"])
})

test("Host plan-context spreads retain authority but serialized and Actor-shaped objects cannot", async () => {
  const context = await capture("root", "workspace")
  const planContext = { ...context, planId: "plan", extra: { ...context.extra, planRevision: 1 } }
  expect(await executionBridge(planContext, "root", "workspace").promise(InstanceState.directory)).toBe("workspace")
  for (const untrusted of [
    JSON.parse(JSON.stringify(context)),
    { sessionID: "root", workspace: "workspace", extra: { coordinatorDispatch: true } },
    {},
    null,
  ]) expect(() => executionBridge(untrusted, "root", "workspace")).toThrow("HOST_EXECUTION_CONTEXT_UNAVAILABLE")
})

test("execution contexts reject another root or workspace", async () => {
  const context = await capture("root", "workspace")
  expect(() => executionBridge(context, "other", "workspace")).toThrow("HOST_EXECUTION_CONTEXT_UNAVAILABLE")
  expect(() => executionBridge(context, "root", "other")).toThrow("HOST_EXECUTION_CONTEXT_UNAVAILABLE")
})

test("context capture without a request fails closed rather than using a global workspace", async () => {
  await expect(Effect.runPromise(captureExecutionContext("root", {}))).rejects.toThrow("InstanceRef not provided")
})

test("direct root repair contexts do not require Tool.Context fields", async () => {
  const context = await Effect.runPromise(captureExecutionContext("root", { promptOps: {}, model: {} }).pipe(
    Effect.provideService(InstanceRef, { directory: "workspace" } as InstanceContext),
  ))
  expect(await executionBridge(context, "root", "workspace").promise(InstanceState.directory)).toBe("workspace")
})
