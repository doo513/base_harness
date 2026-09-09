import { ModelV2 } from "@base-harness/core/model"
import { ProviderV2 } from "@base-harness/core/provider"

export interface ExecutionModelSelection {
  readonly providerID: ProviderV2.ID
  readonly modelID: ModelV2.ID
}

/** A provider descriptor and a prompt model selection are intentionally distinct contracts. */
export function executionModelFromProvider(model: { providerID: string; id: string }): ExecutionModelSelection {
  return requireExecutionModel({ providerID: model.providerID, modelID: model.id })
}

export function requireExecutionModel(input: unknown): ExecutionModelSelection {
  const value = input !== null && typeof input === "object" ? input as Record<string, unknown> : undefined
  if (typeof value?.providerID !== "string" || !value.providerID.trim()
      || typeof value.modelID !== "string" || !value.modelID.trim()) {
    throw Object.assign(new Error("HOST_MODEL_SELECTION_INVALID: providerID and modelID are required"), {
      code: "HOST_MODEL_SELECTION_INVALID",
    })
  }
  return Object.freeze({
    providerID: ProviderV2.ID.make(value.providerID),
    modelID: ModelV2.ID.make(value.modelID),
  })
}
