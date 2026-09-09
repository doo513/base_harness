import { expect, test } from "bun:test"
import { harnessResponseError, unwrapHarnessResponse } from "../src/harness/control-response"

test("legacy Host errors preserve nested message and correlation reference", () => {
  const error = harnessResponseError({
    name: "UnknownError", data: { message: "Unexpected server error.", ref: "err_123" },
  }, 500)
  expect(error.message).toBe("[UnknownError | HTTP 500 | ref err_123] Unexpected server error.")
})

test("typed control rejection keeps the exact Host code and explanation", () => {
  const error = harnessResponseError({
    _tag: "InvalidRequestError", kind: "PLAN_ID_MISMATCH", message: "The reviewed plan ID does not match.",
  }, 400)
  expect(error.message).toBe("[PLAN_ID_MISMATCH | HTTP 400] The reviewed plan ID does not match.")
})

test("nested codes and non-English explanations do not need message classification", () => {
  const message = "\uacc4\ud68d ID\uac00 \ub2e4\ub985\ub2c8\ub2e4."
  expect(harnessResponseError({ data: { code: "PLAN_ID_MISMATCH", message } }).message)
    .toBe("[PLAN_ID_MISMATCH] " + message)
})

test("unknown response objects are not dumped into the terminal", () => {
  const error = harnessResponseError({ stack: "private-stack", authorization: "private-token" })
  expect(error.message).toBe("Harness API request failed")
})

test("successful SDK and direct statuses keep their identity", () => {
  const status = { phase: "plan_ready", readyEligible: false }
  expect(unwrapHarnessResponse<typeof status>({ data: status })).toBe(status)
  expect(unwrapHarnessResponse<typeof status>(status)).toBe(status)
})

test("an SDK error cannot be accepted as a status even if it includes data", () => {
  expect(() => unwrapHarnessResponse({
    data: { phase: "ready" }, error: { kind: "RUN_ACTIVE", message: "Wait for the active run." },
    response: { status: 400 },
  })).toThrow("[RUN_ACTIVE | HTTP 400] Wait for the active run.")
})
