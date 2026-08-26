import { expect, test } from "bun:test"
import { resolve } from "node:path"
import { ProcessVerificationClient, VerificationClientError } from "../src/client"

test("host accepts Ready only from the versioned sidecar response", async () => {
  const client = await ProcessVerificationClient.start(
    {
      runId: "test-run",
      scopeId: "root",
      workspace: process.cwd(),
      goalContract: {
        goal: "exercise protocol",
        acceptance: ["fixture verifier returns Ready"],
      },
    },
    {
      command: [
        process.env.BASE_HARNESS_PYTHON ?? "python",
        resolve(import.meta.dir, "fixture-sidecar.py"),
      ],
    },
  )
  await client.observe({ tool: "write", status: "completed" })
  const status = await client.verify("manual")
  expect(status.outcome).toBe("ready")
  expect(status.readyRef?.trust).toBe("verifier_attested")
  await client.dispose()
})

const startWithMode = (mode: string) =>
  ProcessVerificationClient.start(
    {
      runId: "failure-" + mode,
      scopeId: "root",
      workspace: process.cwd(),
      goalContract: {
        goal: "reject a broken verifier",
        acceptance: ["Ready remains fail-closed"],
      },
    },
    {
      command: [
        process.env.BASE_HARNESS_PYTHON ?? "python",
        resolve(import.meta.dir, "fixture-sidecar.py"),
        mode,
      ],
      timeoutMs: 2_000,
    },
  )

test("malformed NDJSON is fail-closed", async () => {
  const result = startWithMode("malformed")
  await expect(result).rejects.toBeInstanceOf(VerificationClientError)
  await expect(result).rejects.toMatchObject({ failureKind: "harness_protocol_error" })
})

test("sidecar version mismatch is fail-closed", async () => {
  const result = startWithMode("version-mismatch")
  await expect(result).rejects.toBeInstanceOf(VerificationClientError)
  await expect(result).rejects.toMatchObject({
    failureKind: "harness_protocol_version_mismatch",
  })
})

test("sidecar crash is fail-closed", async () => {
  const result = startWithMode("crash")
  await expect(result).rejects.toBeInstanceOf(Error)
})
