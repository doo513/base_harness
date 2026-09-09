type Options = Record<string, unknown>
export interface ReasoningModel {
  id: string
  capabilities: {
    reasoning: boolean
    reasoningEfforts?: { default: "provider_default"; supported: readonly string[] }
  }
  variants?: Record<string, Options>
}

// Transport parameter paths, not model names or inferred effort levels.
const effortPaths = [
  ["reasoningEffort"],
  ["effort"],
  ["reasoning", "effort"],
  ["thinkingConfig", "thinkingLevel"],
  ["reasoningConfig", "maxReasoningEffort"],
  ["modelParams", "reasoning_effort"],
  ["modelParams", "output_config", "effort"],
] as const

const record = (value: unknown): value is Options =>
  typeof value === "object" && value !== null && !Array.isArray(value)

export class ReasoningSelectionError extends Error {
  readonly code = "UNSUPPORTED_REASONING_EFFORT"
}

export function nativeReasoningEffort(options: Options): string | undefined {
  const values = new Set<string>()
  for (const keys of effortPaths) {
    let value: unknown = options
    for (const key of keys) value = record(value) ? value[key] : undefined
    if (value === undefined || value === null) continue
    if (typeof value !== "string" || !value.trim()) {
      throw new ReasoningSelectionError("A named reasoning option must contain a non-empty native string")
    }
    values.add(value)
  }
  if (values.size > 1) throw new ReasoningSelectionError("Conflicting native reasoning options")
  return values.values().next().value
}

export function withoutInferredReasoning(options: Options): Options {
  const result = { ...options }
  for (const keys of effortPaths) {
    let cursor = result
    let found = true
    for (const key of keys.slice(0, -1)) {
      if (!record(cursor[key])) { found = false; break }
      cursor[key] = { ...cursor[key] }
      cursor = cursor[key] as Options
    }
    if (found) delete cursor[keys[keys.length - 1]!]
  }
  return result
}

export function finalizeReasoningCapabilities(
  model: ReasoningModel,
  configured?: Record<string, Options>,
): void {
  const variants = model.variants ?? {}
  const reported = model.capabilities.reasoningEfforts?.supported
  const declared = reported ?? Object.entries(configured ?? {})
    .filter(([id, options]) => options.disabled !== true && nativeReasoningEffort(options) === id)
    .map(([id]) => id)
  const supported = model.capabilities.reasoning
    ? [...new Set(declared)].filter((id) =>
      configured?.[id]?.disabled !== true && variants[id] !== undefined &&
      nativeReasoningEffort(variants[id]!) === id,
    )
    : []
  const allowed = new Set(supported)
  model.variants = Object.fromEntries(Object.entries(variants).filter(([id, options]) => {
    // Non-effort variants (for example numeric budgets) retain their data, but
    // cannot become named reasoning capabilities through a label heuristic.
    return nativeReasoningEffort(options) === undefined || allowed.has(id)
  }))
  model.capabilities.reasoningEfforts = supported.length || reported !== undefined
    ? { default: "provider_default", supported }
    : undefined
}

export function selectReasoningVariant(model: ReasoningModel, requested?: string): string | undefined {
  if (requested === undefined) return undefined
  if (
    !model.capabilities.reasoningEfforts?.supported.includes(requested) ||
    !model.variants?.[requested] ||
    nativeReasoningEffort(model.variants[requested]) !== requested
  ) {
    throw new ReasoningSelectionError(
      "Model " + model.id + " does not declare native reasoning effort " + requested,
    )
  }
  return requested
}

export function assertReasoningOptions(model: ReasoningModel, options: Options, selected?: string): void {
  const actual = nativeReasoningEffort(options)
  if (selected !== undefined && actual !== selected) {
    throw new ReasoningSelectionError("The prepared options replaced the selected native reasoning effort")
  }
  if (actual !== undefined) selectReasoningVariant(model, actual)
}
