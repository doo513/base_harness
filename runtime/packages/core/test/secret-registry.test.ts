import { expect, test } from "bun:test"
import { SecretRegistry, SecretRegistryHub } from "../src/secret-registry"

test("registered values and common encodings are redacted independent of field names", () => {
  const registry = new SecretRegistry()
  const secret = "gemini-token-value-123456"
  registry.register(secret, "provider:google")

  const result = registry.redact({
    arbitrary: `prefix ${secret} suffix`,
    encoded: encodeURIComponent(secret),
    authorization: "not-a-secret-field-value",
  }) as Record<string, string>

  expect(result.arbitrary).not.toContain(secret)
  expect(result.encoded).not.toContain(encodeURIComponent(secret))
  expect(result.authorization).toBe("[REDACTED]")
  expect(registry.findings({ arbitrary: secret })).toHaveLength(1)
})

test("short secrets only redact exact scalars or sensitive fields", () => {
  const registry = new SecretRegistry()
  registry.register("tiny", "test")

  expect(registry.redact("a tiny example")).toBe("a tiny example")
  expect(registry.redact("tiny")).toBe("[REDACTED]")
  expect(registry.redact({ 비밀키: "tiny" })).toEqual({ 비밀키: "[REDACTED]" })
})

test("run registries receive credentials loaded after the run opens", () => {
  const hub = new SecretRegistryHub({})
  hub.openRun("run-1")
  hub.register("late-provider-secret-123456", "provider:late")

  expect(hub.redact("run-1", { arbitrary: "late-provider-secret-123456" })).toEqual({
    arbitrary: "[REDACTED]",
  })
  expect(hub.findings("run-1", { arbitrary: "late-provider-secret-123456" })).toHaveLength(1)
  hub.closeRun("run-1")
})
