import { describe, expect, test } from "bun:test"
import {
  buildConfigOptions,
  buildEffortSelectOption,
  buildModeSelectOption,
  buildModelSelectOption,
  formatCurrentModelId,
  formatVariantName,
  parseModelSelection,
  supportedReasoningVariants,
  type ConfigOptionProvider,
} from "@/acp/config-option"

const providers: ConfigOptionProvider[] = [
  {
    id: "anthropic",
    name: "Anthropic",
    models: {
      "claude/sonnet-4": {
        id: "claude/sonnet-4",
        name: "Claude Sonnet 4",
        capabilities: { reasoning: true, reasoningEfforts: { default: "provider_default", supported: ["high", "very-high"] } },
        variants: {
          default: {},
          high: { reasoningEffort: "high" },
          "very-high": { reasoningEffort: "very-high" },
        },
      },
      "claude-haiku": {
        id: "claude-haiku",
        name: "Claude Haiku",
      },
    },
  },
  {
    id: "openai",
    name: "OpenAI",
    models: {
      "gpt-5": {
        id: "gpt-5",
        name: "GPT-5",
        capabilities: { reasoning: true, reasoningEfforts: { default: "provider_default", supported: ["minimal", "low"] } },
        variants: {
          minimal: { reasoningEffort: "minimal" },
          low: { reasoningEffort: "low" },
        },
      },
    },
  },
]

describe("acp config options", () => {
  test("builds the model select option with ACP verifier category", () => {
    expect(
      buildModelSelectOption({
        providers,
        currentModel: { providerID: "anthropic", modelID: "claude/sonnet-4" },
        currentVariant: "high",
      }),
    ).toEqual({
      id: "model",
      name: "Model",
      category: "model",
      type: "select",
      currentValue: "anthropic/claude/sonnet-4",
      options: [
        { value: "anthropic/claude-haiku", name: "Anthropic/Claude Haiku" },
        { value: "anthropic/claude/sonnet-4", name: "Anthropic/Claude Sonnet 4" },
        { value: "openai/gpt-5", name: "OpenAI/GPT-5" },
      ],
    })
  })

  test("includes variant ids in the model option only when requested", () => {
    const option = buildModelSelectOption({
      providers,
      currentModel: { providerID: "anthropic", modelID: "claude/sonnet-4" },
      currentVariant: "high",
      includeVariants: true,
    })

    expect(option.currentValue).toBe("anthropic/claude/sonnet-4/high")
    if (option.type !== "select") throw new Error("expected select option")
    expect(option.options).toContainEqual({
      value: "anthropic/claude/sonnet-4/high",
      name: "Anthropic/Claude Sonnet 4 (high)",
    })
    expect(option.options).not.toContainEqual({
      value: "anthropic/claude/sonnet-4/default",
      name: "Anthropic/Claude Sonnet 4 (Default)",
    })
  })

  test("unselected effort preserves the provider default", () => {
    expect(buildEffortSelectOption({ variants: ["low", "high"] })).toEqual({
      id: "effort",
      name: "Effort",
      description: "Available effort levels for this model",
      category: "thought_level",
      type: "select",
      currentValue: "provider_default",
      options: [
        { value: "provider_default", name: "Provider default" },
        { value: "low", name: "low" },
        { value: "high", name: "high" },
      ],
    })
  })

  test("effort fallback never chooses the first native level", () => {
    expect(buildEffortSelectOption({ variants: ["minimal", "low"], currentVariant: "missing" })?.currentValue).toBe(
      "provider_default",
    )
  })

  test("omits effort option when there are no variants", () => {
    expect(buildEffortSelectOption({ variants: [] })).toBeUndefined()
  })

  test("builds the mode select option with descriptions when present", () => {
    expect(
      buildModeSelectOption({
        currentModeId: "build",
        modes: [
          { id: "build", name: "Build", description: "Make code changes" },
          { id: "plan", name: "Plan" },
        ],
      }),
    ).toEqual({
      id: "mode",
      name: "Session Mode",
      category: "mode",
      type: "select",
      currentValue: "build",
      options: [
        { value: "build", name: "Build", description: "Make code changes" },
        { value: "plan", name: "Plan" },
      ],
    })
  })

  test("builds full config options with model, effort, and mode in stable order", () => {
    const options = buildConfigOptions({
      providers,
      currentModel: { providerID: "anthropic", modelID: "claude/sonnet-4" },
      currentVariant: "very-high",
      modes: [
        { id: "build", name: "Build" },
        { id: "plan", name: "Plan" },
      ],
      currentModeId: "plan",
    })

    expect(options.map((option) => option.id)).toEqual(["model", "effort", "mode"])
    expect(options.map((option) => option.category)).toEqual(["model", "thought_level", "mode"])
    expect(options[1]?.currentValue).toBe("very-high")
  })

  test("full config options omit effort for models without variants", () => {
    expect(
      buildConfigOptions({
        providers,
        currentModel: { providerID: "anthropic", modelID: "claude-haiku" },
      }).map((option) => option.id),
    ).toEqual(["model"])
  })

  test("parses provider/model selections", () => {
    expect(parseModelSelection("openai/gpt-5", providers)).toEqual({
      model: { providerID: "openai", modelID: "gpt-5" },
    })
  })

  test("parses provider/model/variant selections when the base model exposes that variant", () => {
    expect(parseModelSelection("openai/gpt-5/low", providers)).toEqual({
      model: { providerID: "openai", modelID: "gpt-5" },
      variant: "low",
    })
  })

  test("prefers exact slash-containing model ids before treating the tail as a variant", () => {
    expect(parseModelSelection("anthropic/claude/sonnet-4", providers)).toEqual({
      model: { providerID: "anthropic", modelID: "claude/sonnet-4" },
    })
  })

  test("parses trailing variants for slash-containing model ids", () => {
    expect(parseModelSelection("anthropic/claude/sonnet-4/high", providers)).toEqual({
      model: { providerID: "anthropic", modelID: "claude/sonnet-4" },
      variant: "high",
    })
  })

  test("keeps unknown trailing segments in the model id when they are not valid variants", () => {
    expect(parseModelSelection("anthropic/claude/sonnet-4/missing", providers)).toEqual({
      model: { providerID: "anthropic", modelID: "claude/sonnet-4/missing" },
    })
  })

  test("formats current model ids with and without selected variants", () => {
    expect(
      formatCurrentModelId({
        model: { providerID: "openai", modelID: "gpt-5" },
        variant: "low",
        variants: ["minimal", "low"],
      }),
    ).toBe("openai/gpt-5")
    expect(
      formatCurrentModelId({
        model: { providerID: "openai", modelID: "gpt-5" },
        variant: "low",
        variants: ["minimal", "low"],
        includeVariant: true,
      }),
    ).toBe("openai/gpt-5/low")
  })

  test("formats current model ids with variant fallback", () => {
    expect(
      formatCurrentModelId({
        model: { providerID: "anthropic", modelID: "claude/sonnet-4" },
        variant: "missing",
        variants: ["default", "high"],
        includeVariant: true,
      }),
    ).toBe("anthropic/claude/sonnet-4")
  })

  test("formats variant names for display", () => {
    expect(formatVariantName("very_high-effort")).toBe("very_high-effort")
  })
  test("uses declared native names from a redacted Host catalog without inferring labels", () => {
    const model = {
      id: "fixture", name: "Fixture",
      capabilities: { reasoning: true, reasoningEfforts: { default: "provider_default" as const, supported: ["ServiceExact", "missing"] } },
      variants: {
        ServiceExact: {},
        high: {},
        budget: {},
        unreported: {},
      },
    }
    expect(Object.keys(supportedReasoningVariants(model))).toEqual(["ServiceExact"])
    expect(supportedReasoningVariants({ ...model, capabilities: undefined })).toEqual({})
    expect(supportedReasoningVariants({ ...model, capabilities: { ...model.capabilities, reasoning: false } })).toEqual({})
    const options = buildConfigOptions({
      providers: [{ id: "test", name: "Test", models: { fixture: model } }],
      currentModel: { providerID: "test", modelID: "fixture" },
    })
    const effort = options.find((option) => option.id === "effort")
    expect(effort?.currentValue).toBe("provider_default")
    if (effort?.type !== "select") throw new Error("expected effort selector")
    expect(effort.options).toEqual([
      { value: "provider_default", name: "Provider default" },
      { value: "ServiceExact", name: "ServiceExact" },
    ])
  })
})
