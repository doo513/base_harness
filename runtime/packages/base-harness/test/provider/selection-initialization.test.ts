import { afterEach, expect } from "bun:test"
import { Effect } from "effect"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { ProviderV2 } from "@base-harness/core/provider"
import { Provider } from "@/provider/provider"
import { Env } from "@/env"
import { Plugin } from "@/plugin"
import { disposeAllInstances } from "../fixture/fixture"
import { testEffect } from "../lib/effect"

const saved = new Map<string, string | undefined>()
const configureCredentials = () => Effect.sync(() => {
  for (const key of ["BASE_HARNESS_AUTH_CONTENT", "AWS_BEARER_TOKEN_BEDROCK"]) {
    if (!saved.has(key)) saved.set(key, process.env[key])
  }
  // In-memory fake credentials only: no real auth store is modified.
  process.env.BASE_HARNESS_AUTH_CONTENT = JSON.stringify({
    "amazon-bedrock": { type: "api", key: "fixture-bedrock-selection-token" },
  })
  delete process.env.AWS_BEARER_TOKEN_BEDROCK
})

afterEach(async () => {
  try { await disposeAllInstances() } finally {
    for (const [key, value] of saved) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    saved.clear()
  }
})

const it = testEffect(LayerNode.compile(LayerNode.group([Provider.node, Env.node, Plugin.node])))
const scenarios: Array<{
  name: string; enabled?: string[]; disabled?: string[]; bedrock: boolean; empty?: boolean
}> = [
  { name: "unlisted custom loader is skipped before environment side effects", enabled: ["fixture-selected"], bedrock: false },
  { name: "an empty allowlist initializes no active provider", enabled: [], bedrock: false, empty: true },
  { name: "explicit disable wins over the allowlist", enabled: ["amazon-bedrock", "fixture-selected"], disabled: ["amazon-bedrock"], bedrock: false },
  { name: "an explicitly allowed custom loader still runs", enabled: ["amazon-bedrock"], bedrock: true },
  { name: "omitting the allowlist retains default loader behavior", bedrock: true },
]

for (const scenario of scenarios) {
  it.instance(scenario.name, () => Effect.gen(function* () {
    yield* configureCredentials()
    const providers = yield* Provider.use.list()
    if (scenario.bedrock) {
      expect(providers[ProviderV2.ID.make("amazon-bedrock")]).toBeDefined()
      expect(process.env.AWS_BEARER_TOKEN_BEDROCK).toBe("fixture-bedrock-selection-token")
    } else {
      expect(providers[ProviderV2.ID.make("amazon-bedrock")]).toBeUndefined()
      expect(process.env.AWS_BEARER_TOKEN_BEDROCK).toBeUndefined()
    }
    if (scenario.empty) expect(Object.keys(providers)).toEqual([])
    if (scenario.enabled?.includes("fixture-selected")) {
      expect(providers[ProviderV2.ID.make("fixture-selected")]).toBeDefined()
    }
  }), {
    config: {
      enabled_providers: scenario.enabled,
      disabled_providers: scenario.disabled,
      provider: {
        "fixture-selected": {
          npm: "@ai-sdk/openai-compatible",
          models: { "fixture-model": { name: "Fixture model" } },
          options: { apiKey: "fixture-selected-token" },
        },
      },
    },
  }, 15000)
}
