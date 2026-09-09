import { expect, test } from "bun:test"
import { Effect, Layer } from "effect"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { FSUtil } from "@base-harness/core/fs-util"
import { Auth } from "../../src/auth"

async function withStore(
  options: { exists: () => boolean; data?: unknown; readFails?: boolean; inline?: string },
  body: (auth: Auth.Interface, calls: { probes: number; reads: number }) => Promise<void>,
) {
  const previous = process.env.BASE_HARNESS_AUTH_CONTENT
  if (options.inline === undefined) delete process.env.BASE_HARNESS_AUTH_CONTENT
  else process.env.BASE_HARNESS_AUTH_CONTENT = options.inline
  const calls = { probes: 0, reads: 0 }
  // Only the Auth read surface is provided. No real credential store is accessed.
  const fs = {
    existsSafe: () => Effect.sync(() => { calls.probes++; return options.exists() }),
    readJson: () => Effect.suspend(() => {
      calls.reads++
      return options.readFails
        ? Effect.fail(new FSUtil.FileSystemError({ method: "readJson" }))
        : Effect.succeed(options.data ?? {})
    }),
  } satisfies Pick<FSUtil.Interface, "existsSafe" | "readJson">
  const filesystem = Layer.effect(FSUtil.Service, Effect.gen(function* () {
    const base = yield* FSUtil.Service
    return FSUtil.Service.of({
      ...base,
      ...fs,
      writeJson: () => Effect.die(new Error("Unexpected auth-store write in read fixture")),
    })
  })).pipe(Layer.provide(LayerNode.compile(FSUtil.node)))
  const layer = LayerNode.compile(Auth.node, [[FSUtil.node, filesystem]])
  try {
    await Effect.runPromise(Effect.gen(function* () {
      const auth = yield* Auth.Service
      yield* Effect.promise(() => body(auth, calls))
    }).pipe(Effect.provide(layer)))
  } finally {
    if (previous === undefined) delete process.env.BASE_HARNESS_AUTH_CONTENT
    else process.env.BASE_HARNESS_AUTH_CONTENT = previous
  }
}

test("missing auth store returns empty without attempting JSON read", async () => {
  await withStore({ exists: () => false }, async (auth, calls) => {
    expect(await Effect.runPromise(auth.all())).toEqual({})
    expect(calls).toEqual({ probes: 1, reads: 0 })
  })
})

test("existing store retains valid credentials and filters invalid entries", async () => {
  await withStore({
    exists: () => true,
    data: { fixture: { type: "api", key: "fixture-store-token" }, invalid: { type: "unsupported" } },
  }, async (auth, calls) => {
    expect(await Effect.runPromise(auth.all())).toEqual({
      fixture: { type: "api", key: "fixture-store-token" },
    })
    expect(calls).toEqual({ probes: 1, reads: 1 })
  })
})

test("store removal or read failure after the probe preserves empty fallback", async () => {
  await withStore({ exists: () => true, readFails: true }, async (auth, calls) => {
    expect(await Effect.runPromise(auth.all())).toEqual({})
    expect(calls).toEqual({ probes: 1, reads: 1 })
  })
})

test("a missing result is not cached across subsequent credential loads", async () => {
  let exists = false
  await withStore({
    exists: () => exists,
    data: { fixture: { type: "api", key: "fixture-new-login-token" } },
  }, async (auth, calls) => {
    expect(await Effect.runPromise(auth.all())).toEqual({})
    exists = true
    expect(await Effect.runPromise(auth.get("fixture"))).toEqual({
      type: "api", key: "fixture-new-login-token",
    })
    expect(calls).toEqual({ probes: 2, reads: 1 })
  })
})

test("valid inline credentials do not probe the filesystem", async () => {
  await withStore({
    exists: () => true,
    inline: JSON.stringify({ fixture: { type: "api", key: "fixture-inline-token" } }),
  }, async (auth, calls) => {
    expect(await Effect.runPromise(auth.get("fixture"))).toEqual({
      type: "api", key: "fixture-inline-token",
    })
    expect(calls).toEqual({ probes: 0, reads: 0 })
  })
})

test("malformed inline JSON retains the existing storage fallback", async () => {
  await withStore({ exists: () => false, inline: "{" }, async (auth, calls) => {
    expect(await Effect.runPromise(auth.all())).toEqual({})
    expect(calls).toEqual({ probes: 1, reads: 0 })
  })
})
