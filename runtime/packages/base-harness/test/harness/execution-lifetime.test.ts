import { expect, test } from "bun:test"
import { Cause, Deferred, Effect, Exit } from "effect"
import { runUntilCancelled } from "../../src/harness/execution-lifetime"

test("normal work completion does not cancel the Coordinator run", async () => {
  const run = new AbortController()
  expect(await Effect.runPromise(runUntilCancelled(Effect.succeed("done"), run.signal))).toBe("done")
  expect(run.signal.aborted).toBe(false)
})

test("an already cancelled run cannot start Host work", async () => {
  const run = new AbortController()
  run.abort()
  let started = false
  const exit = await Effect.runPromiseExit(runUntilCancelled(Effect.sync(() => { started = true }), run.signal))
  expect(started).toBe(false)
  expect(Exit.isFailure(exit) && Cause.hasInterruptsOnly(exit.cause)).toBe(true)
})

test("run cancellation interrupts pending work and executes its cleanup", async () => {
  const run = new AbortController()
  const started = Deferred.makeUnsafe<void>()
  let cleaned = false
  const work = Effect.gen(function* () {
    yield* Deferred.succeed(started, undefined)
    yield* Effect.never
  }).pipe(Effect.ensuring(Effect.sync(() => { cleaned = true })))
  const pending = Effect.runPromiseExit(runUntilCancelled(work, run.signal))
  await Effect.runPromise(Deferred.await(started))
  run.abort()
  const exit = await pending
  expect(Exit.isFailure(exit) && Cause.hasInterruptsOnly(exit.cause)).toBe(true)
  expect(cleaned).toBe(true)
})

test("parent stream completion cannot interrupt work owned by another run signal", async () => {
  const stream = new AbortController()
  const run = new AbortController()
  const done = Deferred.makeUnsafe<string>()
  const pending = Effect.runPromise(runUntilCancelled(Deferred.await(done), run.signal))
  stream.abort()
  expect(run.signal.aborted).toBe(false)
  await Effect.runPromise(Deferred.succeed(done, "worker completed"))
  expect(await pending).toBe("worker completed")
})
