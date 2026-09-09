import assert from "node:assert/strict"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime.ts"
import { STARTUP_STAGES, STARTUP_TRACE_PREFIX } from "../packages/base-harness/src/util/startup-trace"

const repo = path.resolve(import.meta.dir, "../..")
const python = process.env.BASE_HARNESS_PYTHON
assert(python, "BASE_HARNESS_PYTHON is required")
const tag = process.env.BASE_HARNESS_VALIDATION_TAG ?? "host-startup-comparison"
assert(/^[A-Za-z0-9_-]+$/.test(tag))
const logRoot = path.join(repo, ".tools/validation")
await mkdir(logRoot, { recursive: true })
const launcher = path.join(repo, "runtime/packages/base-harness/src/source-launcher.ts")
const cwd = path.dirname(path.dirname(launcher))

async function capture(stream) {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let text = "", bytes = 0, truncated = false
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    const available = Math.max(0, 65536 - bytes)
    if (available > 0) text += decoder.decode(value.subarray(0, available), { stream: true })
    bytes += value.byteLength
    if (bytes > 65536) truncated = true
  }
  text += decoder.decode()
  return { text, bytes, truncated }
}

function traceEvents(text, pid) {
  const events = []
  for (const line of text.split(/\r?\n/)) {
    if (!line.startsWith(STARTUP_TRACE_PREFIX) || events.length >= 32) continue
    try {
      const e = JSON.parse(line.slice(STARTUP_TRACE_PREFIX.length))
      if (e.version !== 1 || e.type !== "harness.startup" || e.pid !== pid ||
          !STARTUP_STAGES.includes(e.stage) || typeof e.pureRequested !== "boolean") continue
      if (![e.sequence,e.elapsedMs,e.processUptimeMs,e.pid].every(v => Number.isFinite(v) && v >= 0)) continue
      // Never persist raw stderr, arbitrary fields, paths, arguments or error messages.
      events.push({ version:1,type:"harness.startup",stage:e.stage,sequence:e.sequence,
        elapsedMs:e.elapsedMs,processUptimeMs:e.processUptimeMs,pid:e.pid,pureRequested:e.pureRequested })
    } catch {}
  }
  return events
}

const cases = []
for (const mode of ["default", "pure"]) {
  const fixture = await createLocalRuntimeFixture(python, { reasoner:true, planned:true, exhaustWorker:true })
  const probe = Bun.serve({ hostname:"127.0.0.1",port:0,fetch:() => new Response("") })
  const port = probe.port
  probe.stop(true)
  const env = { ...fixture.env, BASE_HARNESS_TRACE_STARTUP:"1" }
  delete env.BASE_HARNESS_PURE
  if (mode === "pure") env.BASE_HARNESS_PURE = "1"
  let host, stdout, stderr, healthy = false, failureCode
  const started = performance.now()
  let attempts = 0, intentionallyStopped = false
  try {
    host = Bun.spawn({
      cmd:[process.execPath,"run","--conditions=browser",launcher,"serve","--hostname","127.0.0.1","--port",String(port)],
      cwd,env,stdin:"ignore",stdout:"pipe",stderr:"pipe",
    })
    stdout = capture(host.stdout)
    stderr = capture(host.stderr)
    while (performance.now() - started < 30000) {
      if (host.exitCode !== null) { failureCode = "HOST_EXITED_BEFORE_HEALTH"; break }
      attempts++
      try {
        const remaining = Math.max(1, 30000 - (performance.now() - started))
        const response = await fetch("http://127.0.0.1:" + port + "/global/health", {
          signal: AbortSignal.timeout(Math.max(1, Math.floor(Math.min(2000, remaining)))),
        })
        if (response.ok && (await response.json()).healthy === true) { healthy = true; break }
      } catch {}
      await Bun.sleep(200)
    }
    if (!healthy && !failureCode) failureCode = "HOST_STARTUP_DEADLINE"
  } catch {
    failureCode = "HOST_STARTUP_DIAGNOSTIC_ERROR"
  } finally {
    const durationMs = performance.now() - started
    if (host?.exitCode === null) { intentionallyStopped = true; host.kill() }
    if (host) await host.exited
    const out = stdout ? await stdout : { text:"",bytes:0,truncated:false }
    const err = stderr ? await stderr : { text:"",bytes:0,truncated:false }
    const events = host ? traceEvents(err.text, host.pid) : []
    fixture.stop()
    const result = {
      mode,healthy,failureCode,durationMs,attempts,pid:host?.pid,exitCode:host?.exitCode,intentionallyStopped,
      inferenceRequests:fixture.requestLog.length,startupEvents:events,lastObservedStage:events.at(-1)?.stage,
      stdoutBytes:out.bytes,stderrBytes:err.bytes,outputTruncated:out.truncated || err.truncated,
    }
    cases.push(result)
    console.log(JSON.stringify({mode,healthy,failureCode,durationMs,lastObservedStage:result.lastObservedStage}))
  }
}
const result = {
  diagnosticOnly:true,independentEvaluation:false,
  scope:"Two sequential fresh local Host startup observations, not a causal plugin comparison or reliability benchmark",
  success:cases.every(c => c.healthy && c.inferenceRequests === 0 && c.startupEvents.length > 0),
  cases,
}
const output = path.join(logRoot, tag + ".result.json")
await writeFile(output, JSON.stringify(result,null,2), { flag:"wx" })
console.log(JSON.stringify({success:result.success,resultPath:output}))
if (!result.success) process.exitCode = 1
