import { expect, test } from "bun:test"
import { Schema } from "effect"
import { HarnessControlPayload } from "../../src/server/routes/instance/httpapi/groups/session"

test("HTTP selection schema forwards generic and built-in identifiers to Host validation", () => {
  const decode = Schema.decodeUnknownSync(HarnessControlPayload)
  for (const control of [
    { type: "domain.set", domain: "research.Custom" },
    { type: "domain.set", domain: "general" },
    { type: "skill.set", skill: "review.Custom", enabled: true },
    { type: "skill.set", skill: "hackathon", enabled: false },
  ] as const) expect(decode(control)).toEqual(control)
  expect(() => decode({ type: "domain.set", domain: 3 })).toThrow()
  expect(() => decode({ type: "skill.set", skill: "review", enabled: "yes" })).toThrow()
})
