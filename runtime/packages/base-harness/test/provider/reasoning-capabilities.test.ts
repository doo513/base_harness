import { expect, test } from "bun:test"
import {
  assertReasoningOptions,
  finalizeReasoningCapabilities,
  nativeReasoningEffort,
  selectReasoningVariant,
  withoutInferredReasoning,
  type ReasoningModel,
} from "../../src/provider/reasoning-capabilities"

function model(ids: string[], reported?: string[]): ReasoningModel {
  return {
    id: "fixture",
    capabilities: {
      reasoning: true,
      ...(reported ? { reasoningEfforts: { default: "provider_default", supported: reported } } : {}),
    },
    variants: Object.fromEntries(ids.map((id) => [id, { reasoningEffort: id }])),
  }
}

test("explicit configuration publishes only declared native efforts, not guessed presets", () => {
  const value = model(["low", "medium", "high", "max"])
  finalizeReasoningCapabilities(value, { high: { reasoningEffort: "high" }, max: { reasoningEffort: "max" } })
  expect(value.capabilities.reasoningEfforts?.supported).toEqual(["high", "max"])
  expect(Object.keys(value.variants!)).toEqual(["high", "max"])
  expect(selectReasoningVariant(value, "max")).toBe("max")
})

test("unreported preset labels never become capabilities", () => {
  const value = model(["low", "medium", "high"])
  finalizeReasoningCapabilities(value)
  expect(value.capabilities.reasoningEfforts).toBeUndefined()
  expect(value.variants).toEqual({})
  expect(() => selectReasoningVariant(value, "high")).toThrow("does not declare")
})

test("reported service names are preserved verbatim and configuration cannot expand them", () => {
  const value = model(["vendor-deep-v7", "vendor-balanced-v7", "high"], ["vendor-deep-v7", "vendor-balanced-v7"])
  finalizeReasoningCapabilities(value, { high: { reasoningEffort: "high" } })
  expect(value.capabilities.reasoningEfforts?.supported).toEqual(["vendor-deep-v7", "vendor-balanced-v7"])
  expect(selectReasoningVariant(value, "vendor-deep-v7")).toBe("vendor-deep-v7")
  expect(() => selectReasoningVariant(value, "high")).toThrow()
})

test("disabled efforts and aliases do not masquerade as native names", () => {
  const value = model(["high", "max"], ["high", "max"])
  finalizeReasoningCapabilities(value, { high: { disabled: true } })
  expect(value.capabilities.reasoningEfforts?.supported).toEqual(["max"])
  const alias: ReasoningModel = {
    id: "alias", capabilities: { reasoning: true },
    variants: { maximum: { reasoningEffort: "max" } },
  }
  finalizeReasoningCapabilities(alias, alias.variants)
  expect(alias.capabilities.reasoningEfforts).toBeUndefined()
})

test("a default request does not silently substitute an explicit unsupported effort", () => {
  const value = model(["high"], ["high"])
  expect(selectReasoningVariant(value)).toBeUndefined()
  expect(() => selectReasoningVariant(value, "max")).toThrow()
  expect(() => assertReasoningOptions(value, { reasoningEffort: "max" })).toThrow()
})

test("parameter preparation cannot replace the selected effort", () => {
  const value = model(["high", "max"], ["high", "max"])
  expect(() => assertReasoningOptions(value, { reasoningEffort: "high" }, "max")).toThrow()
  expect(() => assertReasoningOptions(value, {}, "max")).toThrow()
  expect(() => assertReasoningOptions(value, { reasoningEffort: "max" }, "max")).not.toThrow()
})

test("native transport paths carry names without a level dictionary", () => {
  for (const options of [
    { effort: "next-native-level" },
    { reasoning: { effort: "next-native-level" } },
    { thinkingConfig: { thinkingLevel: "next-native-level" } },
    { reasoningConfig: { maxReasoningEffort: "next-native-level" } },
  ]) expect(nativeReasoningEffort(options)).toBe("next-native-level")
  expect(() => nativeReasoningEffort({ effort: "one", reasoningEffort: "two" })).toThrow()
})

test("provider-default strips only inferred effort fields and leaves input unchanged", () => {
  const original = { reasoningEffort: "inferred", reasoningSummary: "auto", thinkingConfig: { thinkingLevel: "inferred", includeThoughts: true } }
  expect(withoutInferredReasoning(original)).toEqual({ reasoningSummary: "auto", thinkingConfig: { includeThoughts: true } })
  expect(original.reasoningEffort).toBe("inferred")
})

test("numeric budgets are not relabeled as named effort capabilities", () => {
  const value: ReasoningModel = {
    id: "budget", capabilities: { reasoning: true },
    variants: { deep: { thinkingConfig: { thinkingBudget: 8192 } } },
  }
  finalizeReasoningCapabilities(value, value.variants)
  expect(value.capabilities.reasoningEfforts).toBeUndefined()
  expect(value.variants?.deep).toEqual({ thinkingConfig: { thinkingBudget: 8192 } })
})
