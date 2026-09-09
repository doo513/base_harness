import { expect, test } from "bun:test"
import { providerFetchOptions } from "../../src/provider/fetch-options"

test("Windows Provider fetches do not reuse idle pooled connections", () => {
  const input = { method: "POST", keepalive: true, body: "fixture-body" }
  const output = providerFetchOptions(input, "win32")
  expect(output.keepalive).toBe(false)
  expect(output.timeout).toBe(false)
  expect(output.body).toBe(input.body)
  expect(input.keepalive).toBe(true)
  expect(output).not.toBe(input)
})

test("other platforms retain their existing connection preference", () => {
  expect(providerFetchOptions({}, "linux").keepalive).toBeUndefined()
  expect(providerFetchOptions({ keepalive: true }, "linux").keepalive).toBe(true)
  expect(providerFetchOptions({ keepalive: false }, "darwin").keepalive).toBe(false)
})

test("transport adaptation preserves auth headers and cancellation identity", () => {
  const controller = new AbortController()
  const headers = new Headers({ authorization: "Bearer fixture-only" })
  const input = { method: "POST", headers, signal: controller.signal, body: "request-body" }
  const output = providerFetchOptions(input, "win32")
  expect(output.headers).toBe(headers)
  expect(output.signal).toBe(controller.signal)
  expect(output.body).toBe(input.body)
  expect(output.method).toBe("POST")
})

test("parallel requests keep independent cancellation signals", () => {
  const first = new AbortController(), second = new AbortController()
  const a = providerFetchOptions({ signal: first.signal }, "win32")
  const b = providerFetchOptions({ signal: second.signal }, "win32")
  first.abort()
  expect(a.signal?.aborted).toBe(true)
  expect(b.signal?.aborted).toBe(false)
  expect(a.keepalive).toBe(false)
  expect(b.keepalive).toBe(false)
})
