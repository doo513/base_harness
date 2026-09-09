import { expect, test } from "bun:test"
import { Effect } from "effect"
import { prepare } from "../../src/session/llm/request"

test("unsupported explicit effort fails as typed InvalidRequest before hooks or provider calls", async () => {
  const failure = await Effect.runPromise(Effect.flip(prepare({
    user: { model: { variant: "max" } },
    model: {
      id: "fixture",
      capabilities: { reasoning: true, reasoningEfforts: { default: "provider_default", supported: ["high"] } },
      variants: { high: { reasoningEffort: "high" } },
    },
  } as never)))
  expect(failure).toMatchObject({
    _tag: "LLM.Error",
    reason: { _tag: "InvalidRequest", parameter: "reasoning_effort" },
  })
  expect((failure as { retryable: boolean }).retryable).toBe(false)
})
