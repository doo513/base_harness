import { expect, test } from "bun:test"
import { createHash } from "node:crypto"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { ProcessMeasurementClient } from "../src/measurement-client"
import type { MeasurementRequest, ProcessCapture } from "../src/measurement-types"

const digest = (text: string) => createHash("sha256").update(text).digest("hex")
async function setup() {
  const root = await mkdtemp(join(tmpdir(), "measurement-v5-"))
  await writeFile(join(root, "source.txt"), "real source text")
  const manifestJson = JSON.stringify({ kind: "source", files: [{ path: "source.txt", size: 16, sha256: digest("real source text") }], dependencies: [] })
  const request: MeasurementRequest = {
    requestId: "measurement-1", runId: "run-1", taskId: "root", manifestJson,
    subject: { id: "source-1", revision: 1, kind: "source", sha256: digest(manifestJson) },
    environmentHash: "a".repeat(64),
    check: { schemaVersion: "check-spec-v1", ref: { id: "check-1", revision: 1, sha256: "b".repeat(64) }, author: "model",
      executorId: "python-measurement", supportedSubjects: ["source"], requiredCapabilities: ["read"], timeoutMs: 5000,
      parameters: { kind: "file", path: "source.txt", operator: "equals", expected: "real source text" } },
  }
  return { root, request, cleanup: () => rm(root, { recursive: true, force: true }) }
}
const signal = () => new AbortController().signal

test("real Python v5 reads the bound file; observation is immutable and authenticated only by its pipe", async () => {
  const fixture = await setup()
  const client = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root)
  try {
    const report = await client.measure(fixture.request, signal())
    expect(report.result.execution).toBe("completed")
    expect(report.result).toMatchObject({ findings: [{ name: "sha256" }, { name: "size", observed: 16 }, { name: "file_content", result: "pass" }] })
    expect(client.authenticates(report)).toBe(true)
    expect(client.authenticates(structuredClone(report))).toBe(false)
    expect(Object.isFrozen(report.result)).toBe(true)
    expect(report).not.toHaveProperty("outcome")
    expect(await readFile(join(fixture.root, "source.txt"), "utf8")).toBe("real source text")
  } finally { await client.dispose(); await fixture.cleanup() }
})

test("real admitted process exit 1 produces a failed comparison, not a repair order; replay does not rerun", async () => {
  const fixture = await setup()
  let calls = 0
  const argv = [process.env.BASE_HARNESS_PYTHON ?? "python3", "-c", "print('test output'); raise SystemExit(1)"]
  fixture.request.check.parameters = { kind: "command", argv, cwd: fixture.root, expectedExitCode: 0 }
  fixture.request.check.requiredCapabilities = ["execute"]
  const client = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root, {
    executeCommand: async (_request, abort) => {
      calls++
      abort.throwIfAborted()
      const startedAt = new Date().toISOString()
      const proc = Bun.spawn(argv, { cwd: fixture.root, stdout: "pipe", stderr: "pipe" })
      const stop = () => proc.kill()
      abort.addEventListener("abort", stop, { once: true })
      try {
        const [exitCode, stdout, stderr] = await Promise.all([proc.exited, new Response(proc.stdout).text(), new Response(proc.stderr).text()])
        return { argv, cwd: fixture.root, startedAt, finishedAt: new Date().toISOString(), stdout, stderr, execution: "completed", exitCode }
      } finally { abort.removeEventListener("abort", stop) }
    },
  })
  try {
    const [first, replay] = await Promise.all([client.measure(fixture.request, signal()), client.measure(structuredClone(fixture.request), signal())])
    expect(calls).toBe(1)
    expect(first).toBe(replay)
    expect(first.result.execution).toBe("completed")
    if (first.result.execution === "completed") {
      expect(first.result.findings).toContainEqual({ kind: "comparison", name: "exit_code", operator: "equals", expected: 0, observed: 1, result: "fail" })
      expect(first.result.findings).toContainEqual({ kind: "value", name: "stdout", observed: "test output\n" })
    }
    expect(first).not.toHaveProperty("repairScope")
    const changed = structuredClone(fixture.request); changed.environmentHash = "c".repeat(64)
    await expect(client.measure(changed, signal())).rejects.toThrow("REQUEST_CONFLICT")
    expect(calls).toBe(1)
  } finally { await client.dispose(); await fixture.cleanup() }
})

test("missing command executor returns not_run, and explicit adapter timeout is an error fact", async () => {
  const fixture = await setup()
  const argv = ["registered-check"]
  fixture.request.check.parameters = { kind: "command", argv, cwd: fixture.root, expectedExitCode: 0 }
  fixture.request.check.requiredCapabilities = ["execute"]
  const missing = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root)
  let client: ProcessMeasurementClient | undefined
  try {
    expect((await missing.measure(fixture.request, signal())).result.execution).toBe("not_run")
    client = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root, {
      executeCommand: async (): Promise<ProcessCapture> => ({ argv, cwd: fixture.root, startedAt: new Date().toISOString(), finishedAt: new Date().toISOString(), stdout: "", stderr: "", execution: "error", error: { code: "TIMEOUT", message: "Observed timeout" } }),
    })
    expect((await client.measure(fixture.request, signal())).result).toMatchObject({ execution: "error", error: { code: "TIMEOUT" } })
  } finally { await missing.dispose(); await client?.dispose(); await fixture.cleanup() }
})

test("late cancelled capture is not turned into an observation", async () => {
  const fixture = await setup()
  const argv = ["registered-check"]
  fixture.request.check.parameters = { kind: "command", argv, cwd: fixture.root, expectedExitCode: 0 }
  fixture.request.check.requiredCapabilities = ["execute"]
  let release!: () => void
  let started!: () => void
  const running = new Promise<void>((resolve) => { started = resolve })
  const client = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root, {
    executeCommand: async () => {
      started()
      await new Promise<void>((resolve) => { release = resolve })
      return { argv, cwd: fixture.root, startedAt: new Date().toISOString(), finishedAt: new Date().toISOString(), stdout: "late", stderr: "", execution: "completed", exitCode: 0 }
    },
  })
  try {
    const abort = new AbortController()
    const pending = client.measure(fixture.request, abort.signal)
    const outcome = pending.then(() => "unexpected success", (error: Error) => error.message)
    await running
    abort.abort(); release()
    expect(await outcome).toContain("CANCELLED")
  } finally { await client.dispose(); await fixture.cleanup() }
})

test("malformed command and cross-run request are rejected before executor invocation", async () => {
  const fixture = await setup()
  let calls = 0
  const client = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root, {
    executeCommand: async () => { calls++; throw new Error("must not execute") },
  })
  try {
    await expect(client.measure({ ...fixture.request, runId: "other" }, signal())).rejects.toThrow("BINDING")
    const wrongExecutor = structuredClone(fixture.request)
    wrongExecutor.requestId = "wrong-executor"
    wrongExecutor.check.executorId = "other-verifier"
    await expect(client.measure(wrongExecutor, signal())).rejects.toThrow("EXECUTOR_BINDING")
    fixture.request.check.parameters = { kind: "command", argv: [], cwd: fixture.root, expectedExitCode: 0 }
    await expect(client.measure(fixture.request, signal())).rejects.toThrow("COMMAND_SCHEMA")
    expect(calls).toBe(0)
  } finally { await client.dispose(); await fixture.cleanup() }
})

test("actual timed-out process is stopped and recorded as error, not comparison failure", async () => {
  const fixture = await setup()
  const argv = [process.env.BASE_HARNESS_PYTHON ?? "python3", "-c", "import time; time.sleep(60)"]
  fixture.request.check.parameters = { kind: "command", argv, cwd: fixture.root, expectedExitCode: 0 }
  fixture.request.check.requiredCapabilities = ["execute"]
  fixture.request.check.timeoutMs = 100
  let exited = false
  const client = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root, {
    executeCommand: async (_request, abort) => {
      abort.throwIfAborted()
      const startedAt = new Date().toISOString()
      const proc = Bun.spawn(argv, { cwd: fixture.root, stdout: "pipe", stderr: "pipe" })
      const stop = () => proc.kill()
      abort.addEventListener("abort", stop, { once: true })
      try {
        const [exitCode, stdout, stderr] = await Promise.all([proc.exited, new Response(proc.stdout).text(), new Response(proc.stderr).text()])
        exited = true
        const base = { argv, cwd: fixture.root, startedAt, finishedAt: new Date().toISOString(), stdout, stderr }
        return abort.aborted ? { ...base, execution: "error", error: { code: "TIMEOUT", message: "Process deadline observed" } } :
          { ...base, execution: "completed", exitCode }
      } finally { abort.removeEventListener("abort", stop) }
    },
  })
  try {
    expect((await client.measure(fixture.request, signal())).result).toMatchObject({ execution: "error", error: { code: "TIMEOUT" } })
    expect(exited).toBe(true)
  } finally { await client.dispose(); await fixture.cleanup() }
})

test.each(["wrong-run", "wrong-subject", "ready-field", "wrong-environment"])("corrupt %s response never authenticates and latches protocol failure", async (mode) => {
  const fixture = await setup()
  const client = await ProcessMeasurementClient.start(fixture.request.runId, fixture.root, {
    command: [process.env.BASE_HARNESS_PYTHON ?? "python3", resolve(import.meta.dir, "measurement-fixture.py")],
    env: { MEASUREMENT_FIXTURE_MODE: mode },
  })
  try {
    await expect(client.measure(fixture.request, signal())).rejects.toThrow("MEASUREMENT_RESPONSE")
    await expect(client.measure({ ...fixture.request, requestId: "new" }, signal())).rejects.toThrow("MEASUREMENT_RESPONSE")
  } finally { await client.dispose(); await fixture.cleanup() }
})
