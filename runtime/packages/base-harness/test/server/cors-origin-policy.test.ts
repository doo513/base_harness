import { expect, test } from "bun:test"
import { isAllowedCorsOrigin, isAllowedRequestOrigin } from "@base-harness/server/cors"

test.each(["https://opencode.ai", "https://app.opencode.ai", "https://app.base-harness.ai"])(
  "remote origin %s requires explicit opt-in",
  (origin) => {
    expect(isAllowedCorsOrigin(origin)).toBe(false)
    expect(isAllowedCorsOrigin(origin, { cors: [origin] })).toBe(true)
    expect(isAllowedRequestOrigin(origin, "localhost:4096")).toBe(false)
  },
)

test("configured origins are exact, not domain wildcard grants", () => {
  expect(isAllowedCorsOrigin("https://child.custom.example", { cors: ["https://custom.example"] })).toBe(false)
  expect(isAllowedCorsOrigin("https://custom.example", { cors: ["https://custom.example"] })).toBe(true)
})

test("local UI and same-host requests remain available", () => {
  expect(isAllowedCorsOrigin("http://localhost:3000")).toBe(true)
  expect(isAllowedCorsOrigin("http://127.0.0.1:4096")).toBe(true)
  expect(isAllowedRequestOrigin("https://custom.example", "custom.example")).toBe(true)
  expect(isAllowedCorsOrigin(undefined)).toBe(true)
})
