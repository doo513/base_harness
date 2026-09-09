import { expect, test } from "bun:test"
import { CoordinatorRuntime } from "../src"
import { PersistenceGateway } from "../src/persistence-gateway"

test("Host plan persistence delegates to the existing run-scoped gateway", () => {
  const calls: Array<{ runId: string; value: unknown }> = []
  const clean = { instruction: "[REDACTED]", modelID: "unchanged" }
  class Gateway extends PersistenceGateway {
    override redact<T>(runId: string, value: T): T {
      calls.push({ runId, value })
      return clean as T
    }
  }
  const runtime = new CoordinatorRuntime(undefined, { persistence: new Gateway() })
  const original = { instruction: "fixture-only-secret", modelID: "unchanged" }
  const result = runtime.redactForPersistence("planning-run", original)
  expect(calls).toEqual([{ runId: "planning-run", value: original }])
  expect(result).toBe(clean)
  expect(original.instruction).toBe("fixture-only-secret")
  expect(runtime.status("root").readyEligible).toBe(false)
})
