import { expect, test } from "bun:test"
import { fileURLToPath } from "node:url"
import { createRuntimeFinalizer } from "../../src/effect/app-runtime-lifecycle"

test("cleanup of an unused runtime is a no-op and does not prevent later registration", async () => {
  const finalizer = createRuntimeFinalizer()
  await finalizer.dispose()
  let calls = 0
  finalizer.register(async () => { calls++ })
  await finalizer.dispose()
  expect(calls).toBe(1)
})

test("concurrent runtime disposal shares one pending finalization", async () => {
  const finalizer = createRuntimeFinalizer()
  const gate = Promise.withResolvers<void>()
  let calls = 0
  finalizer.register(() => { calls++; return gate.promise })
  const first = finalizer.dispose()
  expect(finalizer.dispose()).toBe(first)
  await Promise.resolve()
  expect(calls).toBe(1)
  gate.resolve()
  await first
  expect(finalizer.dispose()).toBe(first)
  expect(calls).toBe(1)
})

test("a runtime disposal failure remains visible and is not retried implicitly", async () => {
  const finalizer = createRuntimeFinalizer()
  const error = new Error("Injected disposal failure")
  let calls = 0
  finalizer.register(async () => { calls++; throw error })
  await expect(finalizer.dispose()).rejects.toBe(error)
  await expect(finalizer.dispose()).rejects.toBe(error)
  expect(calls).toBe(1)
})

test("a synchronous disposer error is returned as a rejected promise", async () => {
  const finalizer = createRuntimeFinalizer()
  const error = new Error("Injected synchronous failure")
  finalizer.register(() => { throw error })
  await expect(finalizer.dispose()).rejects.toBe(error)
})

test("another runtime cannot replace a registered finalizer", () => {
  const finalizer = createRuntimeFinalizer()
  const dispose = async () => {}
  finalizer.register(dispose)
  finalizer.register(dispose)
  expect(() => finalizer.register(async () => {})).toThrow("already registered")
})

test("the loaded AppRuntime and teardown hook share the same cleanup in an isolated process", async () => {
  const root = fileURLToPath(new URL("../../", import.meta.url))
  const runtime = new URL("../../src/effect/app-runtime.ts", import.meta.url).href
  const lifecycle = new URL("../../src/effect/app-runtime-lifecycle.ts", import.meta.url).href
  const script = `
    const { AppRuntime } = await import(${JSON.stringify(runtime)})
    const { appRuntimeFinalizer } = await import(${JSON.stringify(lifecycle)})
    const pending = AppRuntime.dispose()
    if (pending !== appRuntimeFinalizer.dispose()) throw new Error("Cleanup identity mismatch")
    await pending
    console.log("loaded-runtime-cleanup-complete")
  `
  const child = Bun.spawn({
    cmd: [process.execPath, "--conditions=browser", "-e", script], cwd: root,
    env: process.env, stdin: "ignore", stdout: "pipe", stderr: "pipe",
  })
  const output = new Response(child.stdout).text()
  const errors = new Response(child.stderr).text()
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; child.kill() }, 20000)
  try {
    const exitCode = await child.exited
    const stdout = await output, stderr = await errors
    expect(timedOut).toBe(false)
    expect({ exitCode, stderr }).toEqual({ exitCode: 0, stderr: "" })
    expect(stdout).toContain("loaded-runtime-cleanup-complete")
  } finally {
    clearTimeout(timer)
    if (child.exitCode === null) { child.kill(); await child.exited }
  }
}, 30000)
