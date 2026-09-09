import { Effect, Exit, Queue, Stream } from "effect"

export class AcpResponseStreamError extends Error {
  constructor(readonly code: "ACP_STDOUT_CLOSED" | "ACP_STDOUT_FAILED") {
    super(code === "ACP_STDOUT_CLOSED" ? "ACP_STDOUT_CLOSED: response stream ended" : "ACP_STDOUT_FAILED: response stream failed")
    this.name = "AcpResponseStreamError"
  }
}

/** Buffered responses survive EOF; subsequent receives fail instead of hanging. */
export const createAcpResponses = (lines: Stream.Stream<string, Error>, onLine: () => void = () => {}) =>
  Effect.gen(function* () {
    const responses = yield* Queue.unbounded<unknown, AcpResponseStreamError>()
    yield* Effect.forkScoped(
      lines.pipe(
        Stream.runForEach((line) => {
          if (line.length === 0) return Effect.void
          onLine()
          let parsed: unknown
          try {
            parsed = JSON.parse(line)
          } catch {
            parsed = { _rawLine: line }
          }
          return Queue.offer(responses, parsed)
        }),
        Effect.onExit((exit) =>
          Queue.fail(responses, new AcpResponseStreamError(Exit.isSuccess(exit) ? "ACP_STDOUT_CLOSED" : "ACP_STDOUT_FAILED")),
        ),
        Effect.ignore,
      ),
    )
    return Queue.take(responses)
  })
