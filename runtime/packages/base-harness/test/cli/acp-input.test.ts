import { describe, expect, test } from "bun:test"
import { PassThrough } from "node:stream"
import { waitForAcpInput } from "../../src/cli/acp-input"

function expectDetached(input: PassThrough) {
  for (const event of ["readable", "end", "error", "close"]) {
    expect(input.listenerCount(event)).toBe(0)
  }
}

describe("ACP input before runtime startup", () => {
  test("returns false for empty EOF without requiring a data consumer", async () => {
    const input = new PassThrough()
    input.end()
    expect(await waitForAcpInput(input)).toBe(false)
    expectDetached(input)
  })

  test("does not treat an open idle pipe as EOF", async () => {
    const input = new PassThrough()
    let settled = false
    const pending = waitForAcpInput(input).then((result) => { settled = true; return result })
    await Promise.resolve()
    expect(settled).toBe(false)
    input.end()
    expect(await pending).toBe(false)
    expectDetached(input)
  })

  test("preserves already buffered request bytes", async () => {
    const input = new PassThrough()
    const bytes = Buffer.from('{"jsonrpc":"2.0","id":1,"method":"initialize"}\n')
    input.write(bytes)
    const length = input.readableLength
    expect(await waitForAcpInput(input)).toBe(true)
    expect(input.readableLength).toBe(length)
    expect(input.read()).toEqual(bytes)
    expectDetached(input)
    input.destroy()
  })

  test("preserves bytes arriving after the wait starts", async () => {
    const input = new PassThrough()
    const pending = waitForAcpInput(input)
    input.write(Buffer.from([0xe3, 0x81, 0x82, 0x0a]))
    expect(await pending).toBe(true)
    expect(input.read()).toEqual(Buffer.from([0xe3, 0x81, 0x82, 0x0a]))
    expectDetached(input)
    input.destroy()
  })

  test("does not discard buffered data when EOF follows it", async () => {
    const input = new PassThrough()
    const bytes = Buffer.from("buffered protocol request\n")
    input.end(bytes)
    expect(await waitForAcpInput(input)).toBe(true)
    expect(input.read()).toEqual(bytes)
    expectDetached(input)
    expect(await waitForAcpInput(input)).toBe(false)
  })

  test("propagates input errors and removes its listeners", async () => {
    const input = new PassThrough()
    const pending = waitForAcpInput(input)
    input.destroy(new Error("fixture-input-error"))
    await expect(pending).rejects.toThrow("fixture-input-error")
    expectDetached(input)
  })

  test("does not silently accept a premature close as clean EOF", async () => {
    const input = new PassThrough()
    const pending = waitForAcpInput(input)
    input.destroy()
    await expect(pending).rejects.toThrow("ACP_STDIN_CLOSED")
    expectDetached(input)
  })
})
