import { expect, test } from "bun:test"
import type { Info } from "../../src/provider/provider"
import { projectProviderPublicInfo } from "../../src/provider/public-info"

const secret = "fixture-private-value+not-a-real-key"
const encoded = encodeURIComponent(secret)
const modalities = { text: true, audio: false, image: false, video: false, pdf: false }

function fixture(): Info {
  return {
    id: "fixture", name: "Fixture service", source: "config", env: ["FIXTURE_AUTH"],
    key: secret,
    options: {
      apiKey: secret, nonstandardCredential: encoded,
      headers: { Authorization: "Bearer " + secret },
      nested: { privateValue: secret },
      fetch: () => { throw new Error("Private fetch must not execute") },
    },
    privateExtension: secret,
    models: {
      model: {
        id: "model", providerID: "fixture", name: "Fixture model", family: "fixture",
        api: { id: "model", npm: "@ai-sdk/openai-compatible", url: "https://user:" + encoded + "@example.invalid/" + encoded + "?token=" + encoded },
        capabilities: {
          ...modalities, temperature: true, reasoning: true, attachment: false, toolcall: true,
          reasoningEfforts: { default: "provider_default", supported: ["vendor-balanced-v2", "vendor-maximum-v7"] },
          input: { ...modalities }, output: { ...modalities }, interleaved: { field: "reasoning_content" },
          privateExtension: secret,
        },
        cost: { input: 1, output: 2, cache: { read: 0.1, write: 0.2 },
          tiers: [{ input: 3, output: 4, cache: { read: 0.3, write: 0.4 }, tier: { type: "context", size: 200000 } }],
          experimentalOver200K: { input: 5, output: 6, cache: { read: 0.5, write: 0.6 } },
        },
        limit: { context: 32768, input: 30000, output: 4096 },
        status: "active", release_date: "2026-09-08",
        options: { nonstandardCredential: secret, endpoint: encoded },
        headers: { Authorization: "Bearer " + secret, "X-Custom-Credential": encoded },
        variants: {
          "vendor-balanced-v2": { reasoningEffort: "exact-balanced-payload", credential: secret },
          "vendor-maximum-v7": { reasoningEffort: "exact-maximum-payload", nested: { value: encoded } },
        },
        privateExtension: secret,
      },
    },
  } as unknown as Info
}

test("credential containers, endpoint credentials and arbitrary extensions never enter provider metadata", () => {
  const result = projectProviderPublicInfo(fixture())
  const serialized = JSON.stringify(result)
  expect(serialized).not.toContain(secret)
  expect(serialized).not.toContain(encoded)
  expect(serialized).not.toContain("example.invalid")
  expect(serialized).not.toContain("privateExtension")
  expect(result.key).toBeUndefined()
  expect(result.options).toEqual({})
  expect(result.models.model!.options).toEqual({})
  expect(result.models.model!.headers).toEqual({})
  expect(result.models.model!.api.url).toBe("")
})

test("provider-native effort names and capabilities survive without exposing private override payloads", () => {
  const result = projectProviderPublicInfo(fixture())
  const model = result.models.model!
  expect(model.capabilities.reasoningEfforts).toEqual({
    default: "provider_default", supported: ["vendor-balanced-v2", "vendor-maximum-v7"],
  })
  expect(model.variants).toEqual({ "vendor-balanced-v2": {}, "vendor-maximum-v7": {} })
  expect(model.capabilities.reasoningEfforts!.supported.filter(effort => model.variants?.[effort] !== undefined))
    .toEqual(["vendor-balanced-v2", "vendor-maximum-v7"])
  expect(JSON.stringify(result)).not.toContain("exact-maximum-payload")
})

test("the Host retains its original authenticated provider, endpoint and reasoning options", () => {
  const original = fixture()
  const projected = projectProviderPublicInfo(original)
  expect(original.key).toBe(secret)
  expect(original.options.apiKey).toBe(secret)
  expect(original.models.model!.headers.Authorization).toBe("Bearer " + secret)
  expect(original.models.model!.api.url).toContain(encoded)
  expect(original.models.model!.variants!["vendor-maximum-v7"]!.reasoningEffort).toBe("exact-maximum-payload")
  projected.env.push("NOT_A_HOST_MUTATION")
  projected.models.model!.capabilities.reasoningEfforts!.supported.push("not-a-real-effort")
  projected.models.model!.cost.tiers![0]!.tier.size = 1
  expect(original.env).toEqual(["FIXTURE_AUTH"])
  expect(original.models.model!.capabilities.reasoningEfforts!.supported).toHaveLength(2)
  expect(original.models.model!.cost.tiers![0]!.tier.size).toBe(200000)
})

test("public projection never invokes provider or model serialization hooks", () => {
  const original = fixture() as Info & { toJSON?: () => unknown }
  original.toJSON = () => { throw new Error("Private serialization hook invoked") }
  ;(original.models.model as any).toJSON = () => { throw new Error("Private model serialization hook invoked") }
  expect(() => JSON.stringify(projectProviderPublicInfo(original))).not.toThrow()
})

test("pricing, limits, connectivity metadata and advertised model identity remain intact", () => {
  const original = fixture(), result = projectProviderPublicInfo(original)
  expect(result.id).toBe(original.id)
  expect(result.source).toBe("config")
  expect(result.env).toEqual(["FIXTURE_AUTH"])
  expect(result.models.model!.api.id).toBe("model")
  expect(result.models.model!.api.npm).toBe("@ai-sdk/openai-compatible")
  expect(result.models.model!.cost).toEqual(original.models.model!.cost)
  expect(result.models.model!.limit).toEqual(original.models.model!.limit)
  expect(result.models.model!.capabilities.interleaved).toEqual({ field: "reasoning_content" })
})

test("models without variants or optional pricing/limits keep their optional shape", () => {
  const original = fixture(), model = original.models.model!
  delete model.variants
  delete model.capabilities.reasoningEfforts
  delete model.cost.tiers
  delete model.cost.experimentalOver200K
  delete model.limit.input
  delete model.family
  model.capabilities.interleaved = false
  const result = projectProviderPublicInfo(original).models.model!
  expect(result.variants).toBeUndefined()
  expect(result.capabilities.reasoningEfforts).toBeUndefined()
  expect(result.cost.tiers).toBeUndefined()
  expect(result.cost.experimentalOver200K).toBeUndefined()
  expect(result.limit.input).toBeUndefined()
  expect(result.family).toBeUndefined()
  expect(result.capabilities.interleaved).toBe(false)
})
