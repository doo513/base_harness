import { expect, test } from "bun:test"
import { MetaReviewDispatchRegistry } from "../../src/harness/meta-review-dispatch"

test("Actor flags and copied objects do not confer meta-review authority", async () => {
  const registry = new MetaReviewDispatchRegistry<object>()
  const context = { extra: { coordinatorDispatch: true, bypassAgentCheck: true }, subagent_type: "meta-review" }
  expect(registry.get(context)).toBeUndefined()
  await registry.run(context, { sessionID: "root", runId: "run", phase: "goal_contract" }, async () => {
    expect(registry.get(context)?.phase).toBe("goal_contract")
    expect(registry.get({ ...context })).toBeUndefined()
    await Promise.resolve()
    expect(registry.get(context)?.runId).toBe("run")
  })
  expect(registry.get(context)).toBeUndefined()
})

test("review context authority is revoked after failure and detached callbacks", async () => {
  const registry = new MetaReviewDispatchRegistry<object>(), context = {}
  let detached!: () => unknown
  await expect(registry.run(context, { sessionID: "root", runId: "run", phase: "plan" }, async () => {
    detached = () => registry.get(context)
    throw new Error("fixture dispatch error")
  })).rejects.toThrow("fixture dispatch error")
  expect(detached()).toBeUndefined()
})

test("a live reviewer context cannot be reentered under another run identity", async () => {
  const registry = new MetaReviewDispatchRegistry<object>(), context = {}
  const dispatch = { sessionID: "root", runId: "run", phase: "plan" as const }
  await registry.run(context, dispatch, async () => {
    await expect(registry.run(context, { ...dispatch, runId: "other" }, async () => undefined)).rejects.toThrow("META_REVIEW_DISPATCH_ACTIVE")
    expect(registry.get(context)?.runId).toBe("run")
  })
})
