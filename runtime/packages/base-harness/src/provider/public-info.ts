import type { Info, Model } from "./provider"

/** Public catalog data, not a serializable copy of a live SDK/provider configuration. */
function publicModel(model: Model): Model {
  const capability = model.capabilities
  const modalities = (value: Model["capabilities"]["input"]) => ({
    text: value.text, audio: value.audio, image: value.image, video: value.video, pdf: value.pdf,
  })
  const cache = (value: Model["cost"]["cache"]) => ({ read: value.read, write: value.write })
  return {
    id: model.id,
    providerID: model.providerID,
    // Endpoint URLs can carry userinfo, signed query parameters or path credentials.
    // Only the Host uses the real URL; the public API keeps its string-shaped field.
    api: { id: model.api.id, npm: model.api.npm, url: "" },
    name: model.name,
    ...(model.family === undefined ? {} : { family: model.family }),
    capabilities: {
      temperature: capability.temperature,
      reasoning: capability.reasoning,
      ...(capability.reasoningEfforts === undefined ? {} : {
        reasoningEfforts: {
          default: capability.reasoningEfforts.default,
          supported: [...capability.reasoningEfforts.supported],
        },
      }),
      attachment: capability.attachment,
      toolcall: capability.toolcall,
      input: modalities(capability.input),
      output: modalities(capability.output),
      interleaved: typeof capability.interleaved === "boolean"
        ? capability.interleaved
        : { field: capability.interleaved.field },
    },
    cost: {
      input: model.cost.input,
      output: model.cost.output,
      cache: cache(model.cost.cache),
      ...(model.cost.tiers === undefined ? {} : {
        tiers: model.cost.tiers.map(item => ({
          input: item.input, output: item.output, cache: cache(item.cache),
          tier: { type: item.tier.type, size: item.tier.size },
        })),
      }),
      ...(model.cost.experimentalOver200K === undefined ? {} : {
        experimentalOver200K: {
          input: model.cost.experimentalOver200K.input,
          output: model.cost.experimentalOver200K.output,
          cache: cache(model.cost.experimentalOver200K.cache),
        },
      }),
    },
    limit: {
      context: model.limit.context, output: model.limit.output,
      ...(model.limit.input === undefined ? {} : { input: model.limit.input }),
    },
    status: model.status,
    options: {},
    headers: {},
    release_date: model.release_date,
    // A client selects the exact advertised name; the Host resolves its private option payload.
    ...(model.variants === undefined ? {} : {
      variants: Object.fromEntries(Object.keys(model.variants).map(name => [name, {}])),
    }),
  }
}

/**
 * Explicit field projection avoids heuristic secret-name matching. Credential containers,
 * arbitrary extensions and toJSON hooks never enter the public response.
 * Display names/IDs remain metadata, not a guarantee that arbitrary user text is secret-free.
 */
export function projectProviderPublicInfo(provider: Info): Info {
  return {
    id: provider.id,
    name: provider.name,
    source: provider.source,
    env: [...provider.env],
    options: {},
    models: Object.fromEntries(Object.entries(provider.models).map(([id, model]) => [id, publicModel(model)])),
  }
}
