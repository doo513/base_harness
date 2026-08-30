import { expect, test } from "bun:test"
import { escalateProfile, normalizeVerificationPolicy, profileForRisk } from "../src/profile"

test("new profile and trigger fields take precedence over legacy fields", () => {
  expect(
    normalizeVerificationPolicy({
      profile: "strict",
      trigger: "auto",
      mode: "manual",
      auto: false,
      maxSameFailureRepairs: 3,
    }),
  ).toEqual({ profile: "strict", trigger: "auto", maxSameFailureRepairs: 3 })
})

test("legacy manual settings normalize for one release", () => {
  expect(normalizeVerificationPolicy({ mode: "manual", auto: false })).toEqual({
    profile: "adaptive",
    trigger: "manual",
    maxSameFailureRepairs: 2,
  })
})

test("risk only escalates the configured profile", () => {
  expect(escalateProfile("fast", profileForRisk("medium"))).toBe("adaptive")
  expect(escalateProfile("adaptive", profileForRisk("critical"))).toBe("strict")
  expect(escalateProfile("strict", profileForRisk("low"))).toBe("strict")
})
