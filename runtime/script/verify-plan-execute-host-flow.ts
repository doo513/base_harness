/**
 * Real Host control API regression for the TUI/headless plan-only -> execute handoff.
 * Uses a local model HTTP fixture, real MCP, real Overlay workers and the Python verifier.
 */
import assert from "node:assert/strict"
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime"

const runtime = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const repo = path.dirname(runtime)
const python = process.env.BASE_HARNESS_PYTHON
if (!python) throw new Error("BASE_HARNESS_PYTHON is required")
const failIntegration = process.argv.includes("--fail-integration")
const cancelPlan = process.argv.includes("--cancel-plan")
assert(!(failIntegration && cancelPlan), "Choose either integration failure or plan cancellation")
const fixture = await createLocalRuntimeFixture(python, { planned: true, reasoner: true, failIntegration })
const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("Reserved", { status: 503 }) })
const port = probe.port
probe.stop(true)
const hostURL = "http://127.0.0.1:" + port
const host = Bun.spawn({
  cmd: [process.execPath, "run", "--conditions=browser",
    path.join(runtime, "packages/base-harness/src/source-launcher.ts"),
    "serve", "--hostname", "127.0.0.1", "--port", String(port)],
  cwd: path.join(runtime, "packages/base-harness"), env: fixture.env,
  stdin: "ignore", stdout: "pipe", stderr: "pipe",
})
const out = new Response(host.stdout).text()
const err = new Response(host.stderr).text()
let timedOut = false
const deadline = setTimeout(() => { timedOut = true; host.kill() }, 150_000)
const logs = path.join(repo, ".tools/validation")
await mkdir(logs, { recursive: true })
const prefix = cancelPlan ? "real-host-plan-cancel"
  : failIntegration ? "real-host-plan-execute-failure" : "real-host-plan-execute"
const directoryQuery = "?directory=" + encodeURIComponent(fixture.workspace)
const statuses: any[] = []
let sessionID = "", planned: any, manuallyChecked: any, cancelled: any, finished: any, plan: any, planningManifest: any, executionManifest: any
let readyArtifact: string | undefined, internalIntegration: any[] = []
let failure: string | undefined, beforeFiles: Array<string | null> = [], afterFiles: Array<string | null> = []

async function request(route: string, body?: unknown) {
  const response = await fetch(hostURL + route + directoryQuery, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(90_000),
  })
  const text = await response.text()
  if (!response.ok) throw new Error("Host " + response.status + " " + route + ": " + text.slice(0, 3000))
  return JSON.parse(text)
}
const fileContents = () => Promise.all(fixture.targets.map(target => readFile(target, "utf8").catch(() => null)))
async function readyArtifacts() {
  const found: Array<{ path: string; value: any }> = []
  let visited = 0
  async function visit(directory: string): Promise<void> {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      if (++visited > 4096) throw new Error("Fixture state inspection exceeded its bound")
      const filename = path.join(directory, entry.name)
      if (entry.isDirectory()) await visit(filename)
      else if (entry.isFile() && entry.name.endsWith(".json")) {
        const value = await readFile(filename, "utf8").then(JSON.parse).catch(() => null)
        if (value?.artifactType === "ready_attestation" || value?.kind === "ready_attestation"
            || (value?.trust === "verifier_attested" && value?.payload?.criterionResults && value?.payload?.evidenceRefs)) {
          found.push({ path: filename, value })
        }
      }
    }
  }
  await visit(fixture.state)
  return found
}

try {
  let available = false
  for (let attempt = 0; attempt < 80; attempt++) {
    if (host.exitCode !== null) throw new Error("Host exited during startup")
    const response = await fetch(hostURL + "/provider" + directoryQuery, { signal: AbortSignal.timeout(1000) }).catch(() => undefined)
    if (response?.ok) { available = true; break }
    await Bun.sleep(500)
  }
  assert(available, "Host provider API must become available")
  sessionID = (await request("/session", {})).id
  const route = "/session/" + sessionID
  await request(route + "/harness/control", { type: "planning.plan_once" })
  await request(route + "/message", {
    model: { providerID: "fixture", modelID: "fixture-reasoner" }, variant: "max",
    parts: [{ type: "text", text: fixture.goal }],
  })
  planned = await request(route + "/harness")
  beforeFiles = await fileContents()
  assert.equal(planned.planningState, "plan_ready")
  assert.equal(planned.workers.length, 0)
  assert.equal(planned.evidenceCount, 0)
  assert.equal(planned.readyEligible, false)
  assert(beforeFiles.every(value => value === null), "Plan-only must not create either result")
  assert.equal((await readyArtifacts()).length, 0, "Plan review cannot issue Ready")
  manuallyChecked = await request(route + "/harness/verify", { reason: "manual" })
  assert.equal(manuallyChecked.planningState, "plan_ready")
  assert.equal(manuallyChecked.readyEligible, false)
  assert.deepEqual(manuallyChecked, await request(route + "/harness"),
    "Manual verification and GET must expose the same Kernel-enriched Host snapshot")
  const reviewsBefore = fixture.requestLog.filter(item => item.reviewPhase).map(item => item.reviewPhase)
  assert.deepEqual(reviewsBefore, ["goal_contract", "plan"])

  if (cancelPlan) {
    const requestsBeforeCancel = fixture.requestLog.length
    cancelled = await request(route + "/harness/cancel", {})
    assert.equal(cancelled.phase, "interrupted")
    assert.equal(cancelled.runId, planned.runId)
    assert.equal(cancelled.activePlanId, planned.activePlanId)
    assert.equal(cancelled.activePlanRevision, planned.activePlanRevision)
    assert.equal(cancelled.domain, planned.domain)
    assert.equal(cancelled.planningState, planned.planningState)
    assert.equal(cancelled.readyEligible, false)
    assert.deepEqual(cancelled, await request(route + "/harness"),
      "Cancellation and GET must expose the same Kernel-enriched Host snapshot")
    finished = await request(route + "/harness/verify", { reason: "manual" })
    assert.deepEqual(finished, cancelled, "Manual verification cannot reopen a cancelled planning run")
    afterFiles = await fileContents()
    assert(afterFiles.every(value => value === null), "Cancelling a plan must not execute its workers")
    assert.equal(finished.workers.length, 0)
    assert.equal((await readyArtifacts()).length, 0)
    assert.equal(fixture.requestLog.length, requestsBeforeCancel)
    statuses.push(cancelled, finished)
  } else {
    const started = await request(route + "/harness/control", { type: "planning.execute", planId: planned.activePlanId })
    assert.notEqual(started.runId, planned.runId, "Execute needs a fresh run, not a UI-only state change")
    assert.equal(started.executionPlan.planningRunId, planned.runId)
    statuses.push(started)
    for (let attempt = 0; attempt < 160; attempt++) {
      finished = await request(route + "/harness")
      statuses.push(finished)
      if (["ready", "blocked", "interrupted"].includes(finished.phase)) break
      if (fixture.requestLog.length > 40) throw new Error("Unexpected model request loop")
      await Bun.sleep(250)
    }
    afterFiles = await fileContents()
    assert(afterFiles.every(value => value === fixture.expected), "Both committed files must match")
    assert.equal(finished.workers.length, 2)
    assert(finished.workers.every((worker: any) => worker.state === "completed"))
    assert.equal(finished.runId, started.runId)
    assert.equal(finished.activePlanId, planned.activePlanId)
    assert.equal(finished.activePlanRevision, planned.activePlanRevision)
    assert.deepEqual(fixture.requestLog.filter(item => item.reviewPhase).map(item => item.reviewPhase), reviewsBefore,
      "Execute must not repeat the two completed meta reviews")
    const executionRequests = fixture.requestLog.filter(item =>
      item.selected || item.reviewPhase || item.workUnitId || item.rootIntegration || item.tools.includes("harness_contract"))
    assert(executionRequests.length > 0)
    assert(executionRequests.every(item => item.model === "fixture-reasoner" && item.reasoningEffort === "max"),
      "Provider-native model and effort must survive every execution boundary")
    assert(fixture.requestLog.some(item => item.rootIntegration), "Root integration must actually reach the model")
    for (const id of ["unit-0", "unit-1"]) {
      assert(fixture.requestLog.some(item => item.workUnitId === id && item.selected === "write"))
    }
    const messages = await request(route + "/message")
    internalIntegration = messages.flatMap((message: any) => message.parts
      .filter((part: any) => part.type === "text" && part.text.includes("base-harness-root-integration-v1"))
      .map((part: any) => ({ messageID: message.info.id, role: message.info.role, synthetic: part.synthetic })))
    assert(internalIntegration.length > 0)
    assert(internalIntegration.every(part => part.synthetic === true), "Internal Host instructions must be marked synthetic")
    const ready = await readyArtifacts()
    if (failIntegration) {
      assert.equal(finished.phase, "blocked")
      assert.equal(finished.failureKind, "model_provider_error")
      assert.equal(finished.readyEligible, false)
      assert.equal(ready.length, 0)
      const retried = await request(route + "/harness/verify", { reason: "manual" })
      assert.equal(retried.phase, "blocked")
      assert.equal(retried.readyEligible, false)
    } else {
      assert.equal(finished.phase, "ready")
      assert.equal(finished.readyEligible, true)
      const verified = ready.find(({ value }) => {
        const payload = value.payload ?? value
        return fixture.criterionIds.every(id => payload.criterionResults?.some((item: any) => item.criterionId === id && item.result === "verified"))
          && fixture.claimIds.every(id => payload.claimResults?.some((item: any) => item.claimId === id && item.result === "verified"))
          && payload.evidenceRefs?.length > 0
      })
      assert(verified, "Ready must be backed by real verifier evidence for both claims")
      readyArtifact = verified.path
    }
    plan = JSON.parse(await readFile(path.join(fixture.state, "base-harness", "plans", planned.activePlanId,
      String(planned.activePlanRevision) + ".json"), "utf8"))
    planningManifest = JSON.parse(await readFile(path.join(fixture.state, "base-harness", "coordinator", planned.runId + ".json"), "utf8"))
    executionManifest = JSON.parse(await readFile(path.join(fixture.state, "base-harness", "coordinator", finished.runId + ".json"), "utf8"))
    assert.equal(plan.runId, planned.runId)
    assert.equal(planningManifest.phase, "plan_ready")
    assert.equal(planningManifest.outcome, null)
    assert.equal(executionManifest.executionPlan.planningRunId, planned.runId)
    assert.equal(executionManifest.executionPlan.goalContractHash, plan.goalContractHash)
  }
} catch (error) {
  failure = error instanceof Error ? error.stack ?? error.message : String(error)
} finally {
  clearTimeout(deadline)
  if (host.exitCode === null) host.kill()
  await host.exited
  fixture.stop()
  await writeFile(path.join(logs, prefix + ".stdout.log"), await out)
  await writeFile(path.join(logs, prefix + ".stderr.log"), await err)
}
const result = {
  success: !failure && !timedOut, expectedIntegrationFailure: failIntegration, expectedCancellation: cancelPlan, timedOut,
  scratch: fixture.scratch, sessionID, planned, manuallyChecked, cancelled, finished, beforeFiles, afterFiles,
  readyArtifact, internalIntegration, plan, planningManifest, executionManifest,
  statuses, requests: fixture.requestLog, failure,
}
await writeFile(path.join(logs, prefix + ".result.json"), JSON.stringify(result, null, 2))
console.log(JSON.stringify({
  success: result.success, expectedIntegrationFailure: failIntegration, expectedCancellation: cancelPlan, scratch: fixture.scratch, sessionID,
  planningRunId: planned?.runId, executionRunId: finished?.runId, phase: finished?.phase,
  planOnlyNoWrites: beforeFiles.length === 2 && beforeFiles.every(value => value === null),
  artifactMatches: afterFiles.length === 2 && afterFiles.every(value => value === fixture.expected),
  modelRequests: fixture.requestLog.length, readyArtifact,
  syntheticIntegration: internalIntegration.length > 0 && internalIntegration.every(part => part.synthetic),
  failure,
}, null, 2))
if (!result.success) process.exitCode = 1
