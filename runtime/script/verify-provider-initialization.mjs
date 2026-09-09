import assert from "node:assert/strict"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime.ts"
import { STARTUP_STAGES, STARTUP_TRACE_PREFIX, PROVIDER_STARTUP_STAGES } from "../packages/base-harness/src/util/startup-trace"

const repo = path.resolve(import.meta.dir, "../..")
const python = process.env.BASE_HARNESS_PYTHON
assert(python, "BASE_HARNESS_PYTHON is required")
const tag = process.env.BASE_HARNESS_VALIDATION_TAG ?? "provider-initialization"
assert(/^[A-Za-z0-9_-]+$/.test(tag))
const authStorage = process.env.BASE_HARNESS_DIAGNOSTIC_AUTH_STORAGE ?? "missing"
assert(["missing", "empty", "inline"].includes(authStorage), "Unsupported diagnostic auth storage")
const fixture = await createLocalRuntimeFixture(python, { reasoner: true })
if (authStorage === "empty") {
  const directory = path.join(fixture.state, "base-harness")
  await mkdir(directory, { recursive: true })
  await writeFile(path.join(directory, "auth.json"), "{}", { flag: "wx" })
}
const launcher = path.join(repo, "runtime/packages/base-harness/src/source-launcher.ts")
const queries = []
let host, stdout, stderr, healthy = false, timedOut = false, failure, exitCode
let phase = "health"
const started = performance.now()
let healthMs
const timer = setTimeout(() => { timedOut = true; host?.kill() }, 90000)

async function capture(stream) {
  const reader = stream.getReader(), decoder = new TextDecoder()
  let text = "", bytes = 0
  while (true) {
    const part = await reader.read()
    if (part.done) break
    const available = Math.max(0, 65536 - bytes)
    if (available) text += decoder.decode(part.value.subarray(0, available), { stream: true })
    bytes += part.value.byteLength
  }
  text += decoder.decode()
  return { text, bytes, truncated: bytes > 65536 }
}

async function responseText(response) {
  assert(response.body, "Response body missing")
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let text = "", bytes = 0
  while (true) {
    const part = await reader.read()
    if (part.done) break
    bytes += part.value.byteLength
    if (bytes > 8 * 1024 * 1024) { await reader.cancel(); throw new Error("Response size limit") }
    text += decoder.decode(part.value, { stream: true })
  }
  return text + decoder.decode()
}

let capturedOut, capturedErr
try {
  const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("") })
  const port = probe.port
  probe.stop(true)
  const url = "http://127.0.0.1:" + port
  host = Bun.spawn({
    cmd: [process.execPath, "run", "--conditions=browser", launcher, "serve", "--hostname", "127.0.0.1", "--port", String(port)],
    cwd: path.dirname(path.dirname(launcher)),
    env: { ...fixture.env, BASE_HARNESS_PURE: "1", BASE_HARNESS_TRACE_STARTUP: "1",
      BASE_HARNESS_AUTH_CONTENT: authStorage === "inline" ? "{}" : undefined },
    stdin: "ignore", stdout: "pipe", stderr: "pipe",
  })
  stdout = capture(host.stdout)
  stderr = capture(host.stderr)
  while (performance.now() - started < 30000 && !timedOut) {
    assert.equal(host.exitCode, null, "Host exited before health")
    try {
      const remaining = Math.max(1, Math.floor(30000 - (performance.now() - started)))
      const response = await fetch(url + "/global/health", { signal: AbortSignal.timeout(Math.min(2000, remaining)) })
      if (response.ok && (await response.json()).healthy === true) { healthy = true; break }
    } catch {}
    await Bun.sleep(200)
  }
  healthMs = performance.now() - started
  assert(healthy, "Health deadline")
  for (const kind of ["first", "cached"]) {
    phase = "catalog_" + kind
    const before = performance.now()
    const response = await fetch(url + "/provider?directory=" + encodeURIComponent(fixture.workspace), {
      signal: AbortSignal.timeout(25000),
    })
    const text = await responseText(response)
    assert(response.ok, "Catalog response failed")
    assert(!text.includes(fixture.token) && !text.includes(encodeURIComponent(fixture.token)), "Credential projection")
    const data = JSON.parse(text)
    const provider = data.all.find(item => item.id === "fixture")
    assert(provider && data.connected.includes("fixture"), "Fixture not connected")
    assert.equal(provider.key, undefined)
    assert.deepEqual(provider.options, {})
    assert.deepEqual(provider.models["fixture-reasoner"].capabilities.reasoningEfforts.supported, ["high", "max"])
    queries.push({ kind, elapsedMs: performance.now() - before, responseBytes: Buffer.byteLength(text),
      connected: true, credentialsOmitted: true, nativeEffortsPreserved: true })
  }
  assert.equal(fixture.requestLog.length, 0, "Unexpected inference")
} catch {
  failure = { phase, code: timedOut ? "DIAGNOSTIC_DEADLINE" : "PROVIDER_INITIALIZATION_DIAGNOSTIC_FAILED" }
} finally {
  clearTimeout(timer)
  if (host?.exitCode === null) host.kill()
  if (host) exitCode = await host.exited
  capturedOut = stdout ? await stdout : { text: "", bytes: 0, truncated: false }
  capturedErr = stderr ? await stderr : { text: "", bytes: 0, truncated: false }
  fixture.stop()
}

const events = []
for (const line of capturedErr.text.split(/\r?\n/)) {
  if (!line.startsWith(STARTUP_TRACE_PREFIX) || events.length >= 32) continue
  try {
    const event = JSON.parse(line.slice(STARTUP_TRACE_PREFIX.length))
    if (event.version !== 1 || event.type !== "harness.startup" || event.pid !== host?.pid ||
        !STARTUP_STAGES.includes(event.stage) || typeof event.pureRequested !== "boolean" ||
        ![event.sequence, event.elapsedMs, event.processUptimeMs, event.pid].every(v => Number.isFinite(v) && v >= 0)) continue
    events.push({ version: 1, type: "harness.startup", stage: event.stage, sequence: event.sequence,
      elapsedMs: event.elapsedMs, processUptimeMs: event.processUptimeMs, pid: event.pid, pureRequested: event.pureRequested })
  } catch {}
}
const missingStages = PROVIDER_STARTUP_STAGES.filter(stage => !events.some(event => event.stage === stage))
const result = {
  diagnosticOnly: true, notHarnessEvidence: true, notIndependentUserValidation: true,
  success: !failure && healthy && queries.length === 2 && missingStages.length === 0,
  phase, failure, timedOut, healthMs, authStorage, queries, startupEvents: events, missingStages,
  inferenceRequests: fixture.requestLog.length,
  lifecycle: { pid: host?.pid, exitCode, intentionallyStoppedAfterDiagnostic: Boolean(host) },
  stdoutBytes: capturedOut.bytes, stderrBytes: capturedErr.bytes,
  outputTruncated: capturedOut.truncated || capturedErr.truncated,
}
const destination = path.join(repo, ".tools/validation", tag + ".result.json")
await mkdir(path.dirname(destination), { recursive: true })
await writeFile(destination, JSON.stringify(result, null, 2), { flag: "wx" })
console.log(JSON.stringify({ success: result.success, resultPath: destination, healthMs, queries, missingStages, failure }))
if (!result.success) process.exitCode = 1
