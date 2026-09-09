/**
 * Real headless plan-only and execute entrypoints, with local model/MCP and real verifier.
 * --local also audits persistence across the two in-process Host lifetimes.
 */
import assert from "node:assert/strict"
import { readFile, readdir, mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime"

const runtime = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const repo = path.dirname(runtime)
const python = process.env.BASE_HARNESS_PYTHON
if (!python) throw new Error("BASE_HARNESS_PYTHON is required")
const local = process.argv.includes("--local")
const standalone = process.argv.includes("--standalone")
const failIntegration = process.argv.includes("--fail-integration")
const revise = process.argv.includes("--revise")
const interruptRevision = process.argv.includes("--interrupt-revision")
assert(!interruptRevision || revise, "--interrupt-revision requires --revise")
const crossDirectory = process.argv.includes("--cross-directory")
const traceEnabled = process.argv.includes("--trace")
const artifactTag = process.env.BASE_HARNESS_FIXTURE_TAG
if (artifactTag) assert(/^[A-Za-z0-9_-]{1,64}$/.test(artifactTag), "Invalid fixture artifact tag")
assert(!crossDirectory || standalone, "--cross-directory requires --standalone")
const fixture = await createLocalRuntimeFixture(python, { planned: true, reasoner: true, failIntegration })
const logs = path.join(repo, ".tools/validation")
await mkdir(logs, { recursive: true })
const prefix = artifactTag ?? "real-headless-plan-" + (local ? "local" : "attach") + (failIntegration ? "-failure" : "") + (standalone ? "-standalone" : "") + (revise ? "-revision" : "") + (crossDirectory ? "-cross-directory" : "")
const launcher = path.join(runtime, "packages/base-harness/src/source-launcher.ts")
const cwd = path.join(runtime, "packages/base-harness")
const query = "?directory=" + encodeURIComponent(fixture.workspace)
const clients: any[] = []
let host: ReturnType<typeof Bun.spawn> | undefined
let hostOut = Promise.resolve(""), hostErr = Promise.resolve(""), hostURL = ""
let planned: any, finished: any, coldPreview: any, readyArtifact: string | undefined, failure: string | undefined
let interruption: any
let revisionRequestOffset = Number.POSITIVE_INFINITY
const traceEntries: Array<Record<string, unknown>> = []
let traceTruncated = false
const debugArgs = traceEnabled ? ["--print-logs", "--log-level", "DEBUG"] : []
function trace(stage: string, detail: Record<string, unknown> = {}) {
  if (!traceEnabled) return
  if (traceEntries.length >= 4096) { traceTruncated = true; return }
  traceEntries.push({ at: Date.now(), stage, ...detail })
}
const launchDirectory = path.join(fixture.scratch, "unrelated-launch")
if (crossDirectory) await mkdir(launchDirectory)

async function request(route: string, timeoutMs = 5000, init?: RequestInit) {
  const started = Date.now()
  trace("host.request", { route, timeoutMs })
  try {
    const response = await fetch(hostURL + route + query, { ...init, signal: AbortSignal.timeout(timeoutMs) })
    trace("host.response", { route, status: response.status, elapsedMs: Date.now() - started })
    assert(response.ok, "Host request " + route + ": " + response.status)
    const body = await response.json()
    trace("host.body", { route, elapsedMs: Date.now() - started })
    return body
  } catch (error) {
    trace("host.request_failed", { route, elapsedMs: Date.now() - started,
      error: (error instanceof Error ? error.name + ": " + error.message : String(error)).slice(0,1024) })
    throw error
  }
}

async function client(name: string, args: string[], limit = 90_000, onSpawn?: (child: ReturnType<typeof Bun.spawn>) => void) {
  const execute = name === "execute" && standalone
  const elsewhere = execute && crossDirectory
  const child = Bun.spawn({
    cmd: [process.execPath, "run", "--conditions=browser", launcher, execute ? "execute" : "run",
      ...(execute ? [planned.activePlanId] : []),
      ...(local ? [] : ["--attach", hostURL]), ...(elsewhere ? [] : ["--dir", fixture.workspace]),
      "--pure", "--auto", "--format", "json", ...debugArgs, ...args],
    cwd: elsewhere ? launchDirectory : cwd,
    env: elsewhere ? { ...fixture.env, BASE_HARNESS_LAUNCH_CWD: launchDirectory } : fixture.env,
    stdin: "ignore", stdout: "pipe", stderr: "pipe",
  })
  onSpawn?.(child)
  trace("client.spawn", { name, pid: child.pid, limitMs: limit, elsewhere })
  const out = new Response(child.stdout).text(), err = new Response(child.stderr).text()
  let timedOut = false
  const started = performance.now()
  const timer = setTimeout(() => {
    timedOut = true
    trace("client.deadline", { name, pid: child.pid, modelRequests: fixture.requestLog.length,
      lastModelRequest: fixture.requestLog.at(-1), modelHttpTrace: fixture.httpTrace.slice(-3) })
    child.kill()
  }, limit)
  const exitCode = await child.exited
  clearTimeout(timer)
  const stdout = await out, stderr = await err
  const invalidJson: string[] = []
  const events = stdout.split(/\r?\n/).filter(Boolean).flatMap(line => {
    try { return [JSON.parse(line)] } catch { invalidJson.push(line); return [] }
  })
  const lastStatus = events.findLast((event: any) => event.type === "harness_status")?.status
  trace("client.exit", { name, pid: child.pid, exitCode, timedOut,
    elapsedMs: Math.round(performance.now() - started),
    lastEventAt: events.at(-1)?.timestamp, phase: lastStatus?.phase, planningState: lastStatus?.planningState,
    tools: events.filter((event: any) => event.type === "tool_use").map((event: any) => event.part?.tool),
    modelRequests: fixture.requestLog.length })
  const result = { name, pid: child.pid, exitCode, timedOut, elapsedMs: Math.round(performance.now() - started), stdout, stderr, events, invalidJson }
  clients.push(result)
  await writeFile(path.join(logs, prefix + "-" + name + ".json"), JSON.stringify(result, null, 2))
  assert(!timedOut, name + " must settle without an observation timeout")
  assert.deepEqual(invalidJson, [], "JSON mode must contain JSON lines only")
  return result
}

const outputs = () => Promise.all(fixture.targets.map(file => readFile(file, "utf8").catch(() => null)))
async function attestations() {
  const found: Array<{ path: string; payload: any }> = []
  let entries = 0
  async function visit(directory: string): Promise<void> {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      assert(++entries <= 4096, "Bounded fixture state")
      const filename = path.join(directory, entry.name)
      if (entry.isDirectory()) await visit(filename)
      else if (entry.isFile() && entry.name.endsWith(".json")) {
        const value = await readFile(filename, "utf8").then(JSON.parse).catch(() => null)
        if (value?.artifactType === "ready_attestation" || value?.kind === "ready_attestation"
            || (value?.trust === "verifier_attested" && value?.payload?.criterionResults && value?.payload?.evidenceRefs)) {
          found.push({ path: filename, payload: value.payload ?? value })
        }
      }
    }
  }
  await visit(fixture.state)
  return found
}

async function startHost() {
    const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("") })
    const port = probe.port
    probe.stop(true)
    hostURL = "http://127.0.0.1:" + port
    host = Bun.spawn({
      cmd: [process.execPath, "run", "--conditions=browser", launcher, "serve", "--hostname", "127.0.0.1", "--port", String(port), ...debugArgs],
      cwd, env: fixture.env, stdin: "ignore", stdout: "pipe", stderr: "pipe",
    })
    trace("host.spawn", { pid: host.pid, url: hostURL })
    hostOut = new Response(host.stdout as ReadableStream).text()
    hostErr = new Response(host.stderr as ReadableStream).text()
    let live = false
    const deadline = performance.now() + 24_000
    for (let attempt = 0; attempt < 80 && performance.now() < deadline; attempt++) {
      assert(host.exitCode === null, "Host stays alive during startup")
      trace("host.probe", { attempt, pid: host.pid })
      try {
        await request("/provider", Math.max(1, Math.min(5000, Math.floor(deadline - performance.now()))))
        live = true
        break
      } catch {}
      await Bun.sleep(Math.max(0, Math.min(300, deadline - performance.now())))
    }
    trace("host.readiness", { pid: host.pid, live })
    assert(live, "Host startup")
}

async function stopHost() {
  if (host?.exitCode === null) host.kill()
  if (host) {
    const exitCode = await host.exited
    trace("host.exit", { pid: host.pid, exitCode })
  }
  host = undefined
}

try {
  if (!local) await startHost()

  const planning = await client("plan", [
    "--model", "fixture/fixture-reasoner", "--variant", "max", "--hackathon", "--plan", fixture.goal,
  ])
  assert.equal(planning.exitCode, 0)
  const planEvent = planning.events.find((event: any) => event.type === "plan_ready")
  assert(planEvent?.status, "Plan-only must emit a typed plan_ready result")
  planned = planEvent.status
  assert.equal(planned.planningState, "plan_ready")
  assert.deepEqual(planned.skills, ["hackathon"])
  assert.equal(planned.readyEligible, false)
  assert((await outputs()).every(value => value === null))
  assert.equal((await attestations()).length, 0)
  if (!local) assert.deepEqual(planned, await request("/session/" + planned.sessionID + "/harness"))

  if (local && revise) {
    const requestsBefore = fixture.requestLog.length
    await startHost()
    coldPreview = await request("/session/" + planned.sessionID + "/harness")
    assert.equal(coldPreview.phase, "plan_ready")
    assert.equal(coldPreview.planningState, "plan_ready")
    assert.equal(coldPreview.planOnly, true)
    assert.equal(coldPreview.activePlanId, planned.activePlanId)
    assert.equal(coldPreview.runId, planned.runId)
    assert.equal(coldPreview.verificationState, "inactive")
    assert.equal(coldPreview.readyEligible, false)
    assert.deepEqual(coldPreview.plan, planned.plan)
    assert.deepEqual(coldPreview.goalContract, planned.goalContract)
    assert.equal(fixture.requestLog.length, requestsBefore, "GET must not call a model")
    assert.equal((await attestations()).length, 0)
    assert((await outputs()).every(value => value === null))
    await stopHost()
  }
  if (revise) {
    const prior = planned
    fixture.reviseGoal()
    revisionRequestOffset = fixture.requestLog.length
    if (interruptRevision) {
      const pause = fixture.pauseNextPlanningRequest()
      let child: ReturnType<typeof Bun.spawn> | undefined
      const pending = client("interrupted-revise", [
        "--session", prior.sessionID, "--model", "fixture/fixture-reasoner", "--variant", "high", fixture.goal,
      ], 90_000, process => { child = process })
      let stopped: any
      try {
        await Promise.race([pause.entered, pending.then(() => { throw new Error("Revision ended before the hold point") })])
        assert(child && child.exitCode === null, "The revision process must be live at the forced interruption")
        child.kill()
        stopped = await pending
        assert.notEqual(stopped.exitCode, 0)
        await stopHost()
      } finally {
        if (child?.exitCode === null) child.kill()
        await pending.catch(() => undefined)
        pause.release()
      }
      await startHost()
      const count = fixture.requestLog.length
      const observed = await request("/session/" + prior.sessionID + "/harness")
      assert.equal(observed.planningState, "awaiting_input")
      assert.equal(observed.planRecovery?.code, "PLAN_REVISION_PENDING")
      assert.equal(observed.planOnly, true)
      assert.equal(observed.readyEligible, false)
      const denied = await client("pending-execute", ["--session", prior.sessionID, "--execute-plan", prior.activePlanId])
      assert.notEqual(denied.exitCode, 0)
      const discarded = await request("/session/" + prior.sessionID + "/harness/control", 5000, {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ type: "planning.discard" }),
      })
      assert.equal(discarded.planningState, "idle")
      assert.equal(discarded.planOnly, false)
      assert.equal(discarded.readyEligible, false)
      assert.equal(fixture.requestLog.length, count, "Recovery controls must not call a model")
      assert((await outputs()).every(value => value === null))
      assert.equal((await attestations()).length, 0)
      interruption = { observed, discarded, childExitCode: stopped.exitCode, priorPlanId: prior.activePlanId }
      if (local) await stopHost()
    }
    // Without interruption, ordinary text inherits plan-only intent. After explicit discard, request a fresh plan.
    const revision = await client("revise", [
      "--session", prior.sessionID, "--model", "fixture/fixture-reasoner", "--variant", "high",
      ...(interruptRevision ? ["--hackathon", "--plan"] : []), fixture.goal,
    ])
    assert.equal(revision.exitCode, 0)
    const revised = revision.events.find((event: any) => event.type === "plan_ready")?.status
    assert(revised, "Ordinary revision must finish as plan_ready, not Ready")
    assert.equal(revised.planOnly, true)
    if (interruptRevision) {
      assert.notEqual(revised.activePlanId, prior.activePlanId)
      assert.equal(revised.activePlanRevision, 1)
      assert.equal(revised.revisesPlan, undefined)
    } else {
      assert.equal(revised.activePlanId, prior.activePlanId)
      assert.equal(revised.activePlanRevision, prior.activePlanRevision + 1)
    }
    assert.notEqual(revised.runId, prior.runId)
    assert.notEqual(revised.goal, prior.goal)
    assert(revised.goal.includes(fixture.goal), "The revised run must own the changed user request")
    assert.notEqual(revised.goalContract.hash, prior.goalContract.hash)
    if (!interruptRevision) assert.deepEqual(revised.revisesPlan, {
      planningRunId: prior.runId, planId: prior.activePlanId,
      planRevision: prior.activePlanRevision, goalContractHash: prior.goalContract.hash,
    })
    assert.equal(revised.readyEligible, false)
    assert((await outputs()).every(value => value === null))
    assert.equal((await attestations()).length, 0)
    assert(!fixture.requestLog.some(item => item.workUnitId || item.rootIntegration))
    planned = revised
    if (interruptRevision) {
      const count = fixture.requestLog.length
      const stale = await client("discarded-plan-execute", ["--session", prior.sessionID, "--execute-plan", prior.activePlanId])
      assert.notEqual(stale.exitCode, 0)
      assert.equal(fixture.requestLog.length, count, "Discarded plan execution must not call a model")
    }
  }

  const reviews = fixture.requestLog.filter(item => item.reviewPhase).map(item => item.reviewPhase)
  if (!local) {
    const requestsBefore = fixture.requestLog.length
    const rejected = await client("wrong-plan", ["--session", planned.sessionID, "--execute-plan", "not-the-reviewed-plan"], 20_000)
    assert.notEqual(rejected.exitCode, 0)
    assert(rejected.events.some((event: any) => event.type === "error"))
    assert.equal(fixture.requestLog.length, requestsBefore)
    const current = await request("/session/" + planned.sessionID + "/harness")
    assert.equal(current.planningState, "plan_ready")
    assert.deepEqual(current.skills, ["hackathon"])
  }
  const execution = await client("execute", standalone ? [] : ["--session", planned.sessionID, "--execute-plan", planned.activePlanId])
  const terminal = execution.events.findLast((event: any) => event.type === "harness_result")
  assert(terminal?.status, "Execution must emit its terminal Host status")
  finished = terminal.status
  assert.notEqual(finished.runId, planned.runId)
  assert.equal(finished.executionPlan.planningRunId, planned.runId)
  assert.equal(finished.goal, planned.goal)
  assert.equal(finished.executionPlan.goalContractHash, planned.goalContract.hash)
  assert.deepEqual(finished.skills, ["hackathon"])
  assert((await outputs()).every(value => value === fixture.expected), "Both verified files must commit")
  assert.deepEqual(fixture.requestLog.filter(item => item.reviewPhase).map(item => item.reviewPhase), reviews)
  const pipeline = fixture.requestLog.map((item, index) => ({ item, index })).filter(({ item }) =>
    item.selected || item.reviewPhase || item.workUnitId || item.rootIntegration || item.tools.includes("harness_contract"))
  assert(pipeline.every(({ item, index }) =>
    item.model === "fixture-reasoner" && item.reasoningEffort === (index >= revisionRequestOffset ? "high" : "max")))
  assert(fixture.requestLog.some(item => item.rootIntegration))
  const ready = await attestations()
  if (failIntegration) {
    assert.notEqual(execution.exitCode, 0)
    assert.equal(finished.phase, "blocked")
    assert.equal(finished.failureKind, "model_provider_error")
    assert.equal(finished.readyEligible, false)
    assert.equal(ready.length, 0)
  } else {
    assert.equal(execution.exitCode, 0)
    assert.equal(finished.phase, "ready")
    assert.equal(finished.readyEligible, true)
    const verified = ready.find(({ payload }) =>
      fixture.criterionIds.every(id => payload.criterionResults?.some((item: any) => item.criterionId === id && item.result === "verified"))
      && fixture.claimIds.every(id => payload.claimResults?.some((item: any) => item.claimId === id && item.result === "verified"))
      && payload.evidenceRefs?.length > 0)
    assert(verified, "Ready needs actual verifier evidence")
    readyArtifact = verified.path
  }
  if (!local) assert.deepEqual(finished, await request("/session/" + planned.sessionID + "/harness"))
} catch (error) {
  failure = error instanceof Error ? error.stack ?? error.message : String(error)
} finally {
  await stopHost()
  fixture.stop()
  await writeFile(path.join(logs, prefix + "-host.stdout.log"), await hostOut)
  await writeFile(path.join(logs, prefix + "-host.stderr.log"), await hostErr)
}
const result = { success: !failure, local, standalone, failIntegration, revise, interruptRevision, interruption, crossDirectory, scratch: fixture.scratch, coldPreview, planned, finished,
  clients, requests: fixture.requestLog, modelHttpTrace: fixture.httpTrace, modelHttpTraceTruncated: fixture.httpTraceTruncated,
  trace: traceEntries, traceTruncated, revisionRequestOffset, expected: fixture.expected, readyArtifact, failure }
const resultPath = path.join(logs, prefix + ".result.json")
await writeFile(resultPath, JSON.stringify(result, null, 2))
console.log(JSON.stringify({ success: result.success, local, standalone, failIntegration, revise, interruptRevision, crossDirectory, scratch: fixture.scratch, resultPath,
  clients: clients.map(({ name, exitCode, timedOut, elapsedMs, invalidJson }) => ({ name, exitCode, timedOut, elapsedMs, invalidJson })),
  planningRunId: planned?.runId, executionRunId: finished?.runId, phase: finished?.phase, readyArtifact, failure }, null, 2))
if (failure) process.exitCode = 1
