import { Effect } from "effect"

/** Bind detached Host work to its Coordinator run, never to a completed LLM stream. */
export function runUntilCancelled<A, E, R>(work: Effect.Effect<A, E, R>, signal: AbortSignal) {
  return Effect.suspend(() => {
    if (signal.aborted) return Effect.interrupt
    const cancelled = Effect.callback<never>((resume) => {
      const abort = () => resume(Effect.interrupt)
      signal.addEventListener("abort", abort, { once: true })
      if (signal.aborted) abort()
      return Effect.sync(() => signal.removeEventListener("abort", abort))
    })
    return Effect.raceFirst(work, cancelled)
  })
}
