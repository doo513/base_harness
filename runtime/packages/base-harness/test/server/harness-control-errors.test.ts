import { expect, test } from "bun:test"
import { Cause, Effect } from "effect"
import { InvalidRequestError } from "../../src/server/routes/instance/httpapi/errors"
import { harnessControlRejection, mapHarnessControlFailure } from "../../src/server/routes/instance/httpapi/handlers/session-errors"

test("typed plan codes become public request errors without copying private details", () => {
  const error = Object.assign(new Error("private workspace path and token"), { code: "PLAN_ID_MISMATCH" })
  const result = harnessControlRejection(error)
  expect(result).toBeInstanceOf(InvalidRequestError)
  expect(result?.kind).toBe("PLAN_ID_MISMATCH")
  expect(result?.message).toContain("reviewed plan")
  expect(JSON.stringify(result)).not.toContain("private")
})

test("plain messages, actor-shaped JSON, and unknown codes are not reclassified", () => {
  expect(harnessControlRejection(new Error("PLAN_ID_MISMATCH"))).toBeUndefined()
  expect(harnessControlRejection({ code: "PLAN_ID_MISMATCH", message: "forged" })).toBeUndefined()
  expect(harnessControlRejection(Object.assign(new Error("failure"), { code: "ECONNRESET" }))).toBeUndefined()
})

test("a rejected Host promise preserves a recognized code across the Effect defect boundary", async () => {
  const result = await Effect.runPromise(Effect.exit(mapHarnessControlFailure(
    Effect.promise(() => Promise.reject(Object.assign(new Error("hidden details"), { code: "PLAN_STALE" }))),
  )))
  if (result._tag !== "Failure") throw new Error("Expected a rejected control")
  const error = Cause.squash(result.cause)
  expect(error).toBeInstanceOf(InvalidRequestError)
  expect((error as InvalidRequestError).kind).toBe("PLAN_STALE")
})

test("unknown defects remain failures and are left to the generic server error boundary", async () => {
  const original = new Error("private internal failure")
  const result = await Effect.runPromise(Effect.exit(mapHarnessControlFailure(Effect.die(original))))
  if (result._tag !== "Failure") throw new Error("Expected a defect")
  expect(Cause.squash(result.cause)).toBe(original)
})

test("successful controls are not rewritten", async () => {
  const status = { phase: "plan_ready", readyEligible: false }
  expect(await Effect.runPromise(mapHarnessControlFailure(Effect.succeed(status)))).toBe(status)
})

test("a blocked planning run has a typed public explanation", () => {
  const result = harnessControlRejection(Object.assign(new Error("private persistence details"), { code: "PLAN_RUN_BLOCKED" }))
  expect(result?.kind).toBe("PLAN_RUN_BLOCKED")
  expect(result?.message).toContain("Host run is blocked")
  expect(result?.message).not.toContain("private")
})

test("Host selection failures expose registered codes without leaking private identifiers", () => {
  for (const code of ["DOMAIN_UNKNOWN", "OVERLAY_UNKNOWN", "DOMAIN_CONTROL_INVALID", "DOMAIN_SKILL_INCOMPATIBLE", "DOMAIN_SKILL_CONFLICT"]) {
    const result = harnessControlRejection(Object.assign(new Error("private custom identifier"), { code }))
    expect(result?.kind).toBe(code)
    expect(result?.message).not.toContain("private")
  }
})

for (const code of ["PLAN_DOMAIN_BINDING_REQUIRED", "PLAN_DOMAIN_BINDING_CHANGED", "PLAN_EXECUTION_GRAPH_CHANGED", "PLAN_RUN_CHANGED"]) {
  test(`${code} crosses the rejected Host promise boundary as an actionable public error`, async () => {
    const result = await Effect.runPromise(Effect.exit(mapHarnessControlFailure(Effect.promise(async () => {
      throw Object.assign(new Error("private workspace and credentials"), { code })
    }))))
    if (result._tag !== "Failure") throw new Error("Expected a request rejection")
    const error = Cause.squash(result.cause)
    expect(error).toBeInstanceOf(InvalidRequestError)
    expect((error as InvalidRequestError).kind).toBe(code)
    expect((error as InvalidRequestError).message.toLowerCase()).toContain("review")
    expect(JSON.stringify(error)).not.toContain("private")
  })
}
