import { expect, test } from "bun:test"
import { selectReasoningVariant } from "../../src/provider/reasoning-capabilities"

test("a variant label alone does not authorize native reasoning", () => {
  expect(() => selectReasoningVariant({
    id: "fixture-model",
    capabilities: { reasoning: true },
    variants: { high: { reasoningEffort: "high" } },
  }, "high")).toThrow("does not declare native reasoning effort")
})

test("explicit native reasoning preserves spelling rather than translating levels", () => {
  const model = {
    id: "fixture-model",
    capabilities: {
      reasoning: true,
      reasoningEfforts: { default: "provider_default" as const, supported: ["ServiceExact"] },
    },
    variants: { ServiceExact: { reasoningEffort: "ServiceExact" } },
  }
  expect(selectReasoningVariant(model, "ServiceExact")).toBe("ServiceExact")
  expect(() => selectReasoningVariant(model, "serviceexact")).toThrow("does not declare native reasoning effort")
})
