import { expect, test } from "bun:test"
import { executionModelFromProvider, requireExecutionModel } from "../../src/harness/model-selection"

test("provider descriptors are explicitly converted without changing their identifiers", () => {
  const descriptor = { providerID: "fixture-provider", id: "org/model-2026", name: "Display name" }
  const selection = executionModelFromProvider(descriptor)
  expect(String(selection.providerID)).toBe("fixture-provider")
  expect(String(selection.modelID)).toBe("org/model-2026")
  expect(Object.isFrozen(selection)).toBe(true)
  expect(descriptor.id).toBe("org/model-2026")
})

test("direct prompt selections retain exact provider and model IDs", () => {
  const value = { providerID: "local", modelID: "model:revision" }
  const selection = requireExecutionModel(value)
  expect(String(selection.providerID)).toBe(value.providerID)
  expect(String(selection.modelID)).toBe(value.modelID)
  expect(selection).not.toBe(value)
})

test("a descriptor cannot masquerade as a prompt selection through an unchecked cast", () => {
  expect(() => requireExecutionModel({ providerID: "fixture", id: "fixture-model" }))
    .toThrow("HOST_MODEL_SELECTION_INVALID")
})

test("malformed selections fail before message creation rather than guessing a model", () => {
  for (const value of [undefined, null, {}, { providerID: "fixture" }, { modelID: "model" },
    { providerID: "", modelID: "model" }, { providerID: "fixture", modelID: " " },
    { providerID: 1, modelID: "model" }, { providerID: "fixture", modelID: 1 }]) {
    expect(() => requireExecutionModel(value)).toThrow("HOST_MODEL_SELECTION_INVALID")
  }
})
