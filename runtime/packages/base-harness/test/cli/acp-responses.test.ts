import { expect, test } from "bun:test"
import { Effect, Stream } from "effect"
import { createAcpResponses } from "../lib/acp-responses"

const terminal = (receive: ReturnType<typeof createAcpResponses> extends Effect.Effect<infer A, any, any> ? A : never) =>
  receive.pipe(
    Effect.map(() => "unexpected_response"),
    Effect.catch((error) => Effect.succeed(error.code)),
  )

test("ACP empty stdout closes the receive queue", async () => {
  await Effect.runPromise(Effect.scoped(Effect.gen(function* () {
    const receive = yield* createAcpResponses(Stream.empty)
    expect(yield* terminal(receive)).toBe("ACP_STDOUT_CLOSED")
    expect(yield* terminal(receive)).toBe("ACP_STDOUT_CLOSED")
  })).pipe(Effect.timeout("2 seconds")))
})

test("ACP buffered responses and malformed lines are retained before EOF", async () => {
  await Effect.runPromise(Effect.scoped(Effect.gen(function* () {
    let count = 0
    const receive = yield* createAcpResponses(Stream.make("", '{"id":1}', "{broken", '{"id":2}'), () => { count++ })
    expect(yield* receive).toEqual({ id: 1 })
    expect(yield* receive).toEqual({ _rawLine: "{broken" })
    expect(yield* receive).toEqual({ id: 2 })
    expect(yield* terminal(receive)).toBe("ACP_STDOUT_CLOSED")
    expect(count).toBe(3)
  })).pipe(Effect.timeout("2 seconds")))
})

test("ACP stream failure preserves buffered responses and surfaces a typed error", async () => {
  await Effect.runPromise(Effect.scoped(Effect.gen(function* () {
    const receive = yield* createAcpResponses(
      Stream.concat(Stream.make('{"id":1}'), Stream.fail(new Error("sensitive transport details"))),
    )
    expect(yield* receive).toEqual({ id: 1 })
    expect(yield* terminal(receive)).toBe("ACP_STDOUT_FAILED")
    const message = yield* receive.pipe(
      Effect.map(() => "unexpected_response"),
      Effect.catch((error) => Effect.succeed(error.message)),
    )
    expect(message).not.toContain("sensitive")
  })).pipe(Effect.timeout("2 seconds")))
})
