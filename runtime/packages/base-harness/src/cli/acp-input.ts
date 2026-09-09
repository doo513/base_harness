import type { Readable } from "node:stream"

/**
 * Peek without consuming protocol bytes or switching stdin into flowing mode.
 * Empty EOF needs no runtime; buffered input stays owned by the ACP transport.
 */
export function waitForAcpInput(input: Readable): Promise<boolean> {
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = (hasInput: boolean, error?: Error) => {
      if (settled) return
      settled = true
      input.off("readable", readable)
      input.off("end", ended)
      input.off("error", failed)
      input.off("close", closed)
      if (error) reject(error)
      else resolve(hasInput)
    }
    const readable = () => {
      if (input.errored) return finish(false, input.errored)
      if (input.readableLength > 0) return finish(true)
      if (input.readableEnded) return finish(false)
      if (input.destroyed) return finish(false, new Error("ACP_STDIN_CLOSED"))
      // read(0) requests EOF notification without consuming a byte.
      input.read(0)
    }
    const ended = () => finish(false)
    const failed = (error: Error) => finish(false, error)
    const closed = () => finish(false, input.readableEnded ? undefined : new Error("ACP_STDIN_CLOSED"))
    input.on("readable", readable)
    input.once("end", ended)
    input.once("error", failed)
    input.once("close", closed)
    readable()
  })
}
