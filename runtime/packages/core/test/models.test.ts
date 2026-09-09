import { describe, expect, beforeAll, beforeEach, afterAll } from "bun:test"
import { Effect, Layer, Ref } from "effect"
import { HttpClient, HttpClientResponse } from "effect/unstable/http"
import { AppNodeBuilder } from "@base-harness/core/effect/app-node-builder"
import { LayerNodePlatform } from "@base-harness/core/effect/app-node-platform"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { Flag } from "@base-harness/core/flag/flag"
import { Global } from "@base-harness/core/global"
import { ModelsDev } from "@base-harness/core/models-dev"
import { it } from "./lib/effect"
import { readFile, rm, writeFile, utimes, mkdir, mkdtemp } from "fs/promises"
import os from "node:os"
import bundledModels from "../src/models-catalog.json" with { type: "json" }
import path from "path"

// Default operation uses the bundled local catalog. Remote-cache tests opt in
// explicitly and use only the injected HTTP client and a disposable cache.
const ORIGINAL_MODELS_PATH = Flag.BASE_HARNESS_MODELS_PATH
const ORIGINAL_MODELS_URL = Flag.BASE_HARNESS_MODELS_URL
const ORIGINAL_DISABLE_FETCH = Flag.BASE_HARNESS_DISABLE_MODELS_FETCH
const ORIGINAL_CACHE_PATH = Global.Path.cache
let cacheDirectory: string | undefined
let cacheFile: string
beforeAll(async () => {
  cacheDirectory = await mkdtemp(path.join(os.tmpdir(), "base-harness-models-test-"))
  cacheFile = path.join(cacheDirectory, "models.json")
  Global.Path.cache = cacheDirectory
  Flag.BASE_HARNESS_MODELS_PATH = undefined
  Flag.BASE_HARNESS_MODELS_URL = "https://models.dev"
  Flag.BASE_HARNESS_DISABLE_MODELS_FETCH = true
})
afterAll(async () => {
  Flag.BASE_HARNESS_MODELS_PATH = ORIGINAL_MODELS_PATH
  Flag.BASE_HARNESS_MODELS_URL = ORIGINAL_MODELS_URL
  Flag.BASE_HARNESS_DISABLE_MODELS_FETCH = ORIGINAL_DISABLE_FETCH
  Global.Path.cache = ORIGINAL_CACHE_PATH
  if (cacheDirectory) await rm(cacheDirectory, { recursive: true, force: true })
})

const fixture: Record<string, ModelsDev.Provider> = {
  acme: {
    id: "acme",
    name: "Acme",
    env: ["ACME_API_KEY"],
    models: {
      "acme-1": {
        id: "acme-1",
        name: "Acme One",
        release_date: "2026-01-01",
        attachment: false,
        reasoning: false,
        temperature: true,
        tool_call: true,
        limit: { context: 128000, output: 8192 },
      },
    },
  },
}

const fixture2: Record<string, ModelsDev.Provider> = {
  beta: {
    id: "beta",
    name: "Beta",
    env: ["BETA_API_KEY"],
    models: {
      "beta-1": {
        id: "beta-1",
        name: "Beta One",
        release_date: "2026-02-01",
        attachment: false,
        reasoning: true,
        temperature: false,
        tool_call: false,
        limit: { context: 64000, output: 4096 },
      },
    },
  },
}

interface MockState {
  body: string
  status: number
  calls: Array<{ url: string; userAgent: string | null }>
}

const makeMockClient = (state: Ref.Ref<MockState>) =>
  HttpClient.make((request) =>
    Effect.gen(function* () {
      yield* Ref.update(state, (s) => ({
        ...s,
        calls: [...s.calls, { url: request.url, userAgent: request.headers["user-agent"] ?? null }],
      }))
      const s = yield* Ref.get(state)
      return HttpClientResponse.fromWeb(request, new Response(s.body, { status: s.status }))
    }),
  )

const buildLayer = (state: Ref.Ref<MockState>) =>
  // Layer.fresh is required because the ModelsDev implementation is a module-level Layer constant,
  // and Effect.provide uses a process-global MemoMap by default — without fresh,
  // every test would reuse the cachedInvalidateWithTTL state from the first run.
  Layer.fresh(
    AppNodeBuilder.build(ModelsDev.node, [
      [LayerNodePlatform.httpClient, Layer.succeed(HttpClient.HttpClient, makeMockClient(state))],
    ]),
  )

const writeCacheText = (text: string, mtimeMs?: number) =>
  Effect.promise(async () => {
    await mkdir(Global.Path.cache, { recursive: true })
    await writeFile(cacheFile, text)
    if (mtimeMs !== undefined) {
      const t = mtimeMs / 1000
      await utimes(cacheFile, t, t)
    }
  })

const writeCache = (data: object, mtimeMs?: number) => writeCacheText(JSON.stringify(data), mtimeMs)

const provided = <A, E>(state: Ref.Ref<MockState>, eff: Effect.Effect<A, E, ModelsDev.Service>) =>
  eff.pipe(Effect.provide(buildLayer(state)))

beforeEach(async () => {
  await rm(cacheFile, { force: true })
})

const initialState: MockState = {
  body: JSON.stringify(fixture),
  status: 200,
  calls: [],
}

describe("ModelsDev Service", () => {
  it.live("default catalog stays local and does not refresh a remote cache without opt-in", () =>
    Effect.gen(function* () {
      yield* writeCache(fixture)
      const state = yield* Ref.make(initialState)
      const result = yield* Effect.acquireUseRelease(
        Effect.sync(() => {
          const previous = Flag.BASE_HARNESS_MODELS_URL
          Flag.BASE_HARNESS_MODELS_URL = undefined
          return previous
        }),
        () => provided(state, Effect.gen(function* () {
          const service = yield* ModelsDev.Service
          const catalog = yield* service.get()
          yield* service.refresh(true)
          return catalog
        })),
        (previous) => Effect.sync(() => { Flag.BASE_HARNESS_MODELS_URL = previous }),
      )
      expect(Object.is(result, bundledModels)).toBe(true)
      expect((yield* Ref.get(state)).calls).toEqual([])
      expect(yield* Effect.promise(() => readFile(cacheFile, "utf8"))).toBe(JSON.stringify(fixture))
    }),
  )

  it.live("get() returns providers from disk when cache file exists", () =>
    Effect.gen(function* () {
      yield* writeCache(fixture)
      const state = yield* Ref.make(initialState)
      const result = yield* provided(
        state,
        ModelsDev.Service.use((s) => s.get()),
      )
      expect(result).toEqual(fixture)
      const final = yield* Ref.get(state)
      expect(final.calls).toEqual([])
    }),
  )

  it.live("get() returns an empty catalog for an explicitly configured URL with no cache and fetching disabled", () =>
    Effect.gen(function* () {
      const state = yield* Ref.make(initialState)
      const result = yield* provided(
        state,
        ModelsDev.Service.use((s) => s.get()),
      )
      expect(result).toEqual({})
      const final = yield* Ref.get(state)
      expect(final.calls).toEqual([])
    }),
  )

  it.live("get() recovers from a corrupted cache file by fetching a fresh catalog", () =>
    Effect.gen(function* () {
      yield* writeCacheText("{")
      const state = yield* Ref.make({ ...initialState, body: JSON.stringify(fixture2) })
      const context = yield* Layer.build(buildLayer(state))
      const result = yield* Effect.acquireUseRelease(
        Effect.sync(() => {
          Flag.BASE_HARNESS_DISABLE_MODELS_FETCH = false
        }),
        () => ModelsDev.Service.use((s) => s.get()).pipe(Effect.provide(context)),
        () =>
          Effect.sync(() => {
            Flag.BASE_HARNESS_DISABLE_MODELS_FETCH = true
          }),
      )
      expect(result).toEqual(fixture2)
      expect(yield* Effect.promise(() => readFile(cacheFile, "utf8"))).toBe(JSON.stringify(fixture2))
      const final = yield* Ref.get(state)
      expect(final.calls.length).toBe(1)
    }),
  )

  it.live("get() is single-flight under concurrent calls", () =>
    Effect.gen(function* () {
      yield* writeCache(fixture)
      const state = yield* Ref.make(initialState)
      const results = yield* provided(
        state,
        Effect.gen(function* () {
          const svc = yield* ModelsDev.Service
          return yield* Effect.all([svc.get(), svc.get(), svc.get(), svc.get(), svc.get()], {
            concurrency: "unbounded",
          })
        }),
      )
      for (const result of results) expect(result).toEqual(fixture)
    }),
  )

  it.live("get() caches across calls (later disk writes are ignored until invalidate)", () =>
    Effect.gen(function* () {
      yield* writeCache(fixture)
      const state = yield* Ref.make(initialState)
      const first = yield* provided(
        state,
        Effect.gen(function* () {
          const svc = yield* ModelsDev.Service
          const a = yield* svc.get()
          // mutate disk between calls — cache should mask the change
          yield* writeCache(fixture2)
          const b = yield* svc.get()
          return { a, b }
        }),
      )
      expect(first.a).toEqual(fixture)
      expect(first.b).toEqual(fixture)
    }),
  )

  it.live("refresh(true) fetches via HttpClient and updates the cache", () =>
    Effect.gen(function* () {
      yield* writeCache(fixture)
      const state = yield* Ref.make({ ...initialState, body: JSON.stringify(fixture2) })
      const result = yield* provided(
        state,
        Effect.gen(function* () {
          const svc = yield* ModelsDev.Service
          const before = yield* svc.get()
          yield* svc.refresh(true)
          const after = yield* svc.get()
          return { before, after }
        }),
      )
      expect(result.before).toEqual(fixture)
      expect(result.after).toEqual(fixture2)
      const final = yield* Ref.get(state)
      expect(final.calls.length).toBe(1)
      expect(final.calls[0].url).toContain("/api.json")
      expect(final.calls[0].userAgent).toContain("/cli")
    }),
  )

  it.live("refresh(false) skips fetch when on-disk file is fresh", () =>
    Effect.gen(function* () {
      // Fresh: mtime within the 5-minute TTL.
      yield* writeCache(fixture, Date.now() - 1000)
      const state = yield* Ref.make({ ...initialState, body: JSON.stringify(fixture2) })
      yield* provided(
        state,
        ModelsDev.Service.use((s) => s.refresh(false)),
      )
      const final = yield* Ref.get(state)
      expect(final.calls).toEqual([])
    }),
  )

  it.live("refresh(false) fetches when on-disk file is stale", () =>
    Effect.gen(function* () {
      // Stale: mtime 10 minutes ago, beyond the 5-minute TTL.
      yield* writeCache(fixture, Date.now() - 10 * 60 * 1000)
      const state = yield* Ref.make({ ...initialState, body: JSON.stringify(fixture2) })
      const after = yield* provided(
        state,
        Effect.gen(function* () {
          const svc = yield* ModelsDev.Service
          yield* svc.refresh(false)
          return yield* svc.get()
        }),
      )
      const final = yield* Ref.get(state)
      expect(final.calls.length).toBe(1)
      expect(after).toEqual(fixture2)
    }),
  )

  it.live("refresh swallows HTTP errors and leaves cache intact", () =>
    Effect.gen(function* () {
      yield* writeCache(fixture)
      const state = yield* Ref.make({ ...initialState, status: 500, body: "boom" })
      const result = yield* provided(
        state,
        Effect.gen(function* () {
          const svc = yield* ModelsDev.Service
          yield* svc.refresh(true)
          return yield* svc.get()
        }),
      )
      expect(result).toEqual(fixture)
      // retryTransient retries 5xx, so calls may be > 1.
      const final = yield* Ref.get(state)
      expect(final.calls.length).toBeGreaterThanOrEqual(1)
    }),
  )
})
