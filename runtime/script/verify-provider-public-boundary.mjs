import assert from "node:assert/strict"
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime.ts"

const repo = path.resolve(import.meta.dir, "../..")
const python = process.env.BASE_HARNESS_PYTHON
assert(python, "BASE_HARNESS_PYTHON is required")
const failIntegration = process.env.BASE_HARNESS_FIXTURE_FAIL_INTEGRATION === "1"
const repairWorker = process.env.BASE_HARNESS_FIXTURE_REPAIR_WORKER === "1"
const exhaustWorker = process.env.BASE_HARNESS_FIXTURE_EXHAUST_WORKER === "1"
assert([failIntegration, repairWorker, exhaustWorker].filter(Boolean).length <= 1, "Select one failure scenario per diagnostic run")
const planned = failIntegration || repairWorker || exhaustWorker || process.env.BASE_HARNESS_FIXTURE_PLANNED === "1"
const fixture = await createLocalRuntimeFixture(python, { reasoner: true, planned, failIntegration, repairWorker, exhaustWorker })
const launcher = path.join(repo, "runtime/packages/base-harness/src/source-launcher.ts")
const cwd = path.dirname(path.dirname(launcher))
const logRoot = path.join(repo, ".tools/validation")
const tag = process.env.BASE_HARNESS_VALIDATION_TAG ?? "provider-public-boundary"
assert(/^[A-Za-z0-9_-]+$/.test(tag), "Validation tag must be one filename component")
await mkdir(logRoot, { recursive: true })
const query = "?directory=" + encodeURIComponent(fixture.workspace)
let host, client, hostURL, hostStreams, clientStreams, finalStatus, failure, timedOut = false
const checks = [], timings = {}, lifecycle = {}
const deadline = setTimeout(() => {
  timedOut = true
  client?.kill()
  host?.kill()
}, 150000)

async function request(route, body, timeoutMs = 25000) {
  const start = performance.now()
  const response = await fetch(hostURL + route + query, {
    method: body === undefined ? "GET" : "POST",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  })
  const content = await response.text()
  timings[route] = performance.now() - start
  assert(response.ok, route + ": HTTP " + response.status + " " + content.slice(0,300))
  return { value: JSON.parse(content), content }
}

function assertMetadata(route, response, providers) {
  assert(!response.content.includes(fixture.token), route + " contains the fixture credential")
  assert(!response.content.includes(encodeURIComponent(fixture.token)), route + " contains an encoded credential")
  const provider = providers.find(item => item.id === "fixture")
  assert(provider, "Fixture provider is still discoverable")
  assert.equal(provider.key, undefined)
  assert.deepEqual(provider.options, {})
  const model = provider.models["fixture-reasoner"]
  assert(model, "Reasoning model is still discoverable")
  assert.equal(model.api.url, "")
  assert.deepEqual(model.options, {})
  assert.deepEqual(model.headers, {})
  assert.deepEqual(model.capabilities.reasoningEfforts.supported, ["high","max"])
  assert.deepEqual(model.variants, { high: {}, max: {} })
  checks.push({ route, credentialsOmitted: true, privateOptionsOmitted: true, exactEfforts: ["high","max"] })
}

async function inspectRootReadyArtifacts(runId, scopeId) {
  const pending = [path.join(fixture.state, "base-harness", "runs")]
  let entriesVisited = 0, jsonFilesRead = 0, runArtifacts = 0
  const readyArtifacts = [], rejections = [], scopeAttestations = []
  while (pending.length) {
    const directory = pending.pop()
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      assert(++entriesVisited <= 512, "Artifact inspection exceeded its bounded fixture size")
      const filename = path.join(directory, entry.name)
      if (entry.isDirectory()) pending.push(filename)
      else if (entry.isFile() && entry.name.endsWith(".json")) {
        const artifact = JSON.parse(await readFile(filename, "utf8"))
        jsonFilesRead++
        if (artifact.runId !== runId) continue
        runArtifacts++
        if (artifact.artifactType === "ready_attestation" && artifact.payload?.scopeId === scopeId) {
          readyArtifacts.push({ path: filename, payload: artifact.payload })
        }
        if (artifact.artifactType === "verification_rejection") {
          rejections.push({ path: filename, createdAt: artifact.createdAt, payload: artifact.payload })
        }
        if (artifact.artifactType === "scope_attestation") {
          scopeAttestations.push({ path: filename, createdAt: artifact.createdAt, payload: artifact.payload })
        }
      }
    }
  }
  assert(runArtifacts > 0, "No current run artifacts were examined")
  return { readyArtifacts, rejections, scopeAttestations, entriesVisited, jsonFilesRead, runArtifacts }
}

try {
  const probe = Bun.serve({ hostname:"127.0.0.1", port:0, fetch:() => new Response("") })
  const port = probe.port
  probe.stop(true)
  hostURL = "http://127.0.0.1:" + port
  host = Bun.spawn({
    cmd:[process.execPath,"run","--conditions=browser",launcher,"serve","--hostname","127.0.0.1","--port",String(port)],
    cwd, env:fixture.env, stdin:"ignore", stdout:"pipe", stderr:"pipe",
  })
  lifecycle.hostPID = host.pid
  hostStreams = { stdout: new Response(host.stdout).text(), stderr: new Response(host.stderr).text() }
  const startup = performance.now()
  let ready = false
  const attempts = []
  while (performance.now() - startup < 30000) {
    assert.equal(host.exitCode, null, "Host exited before health readiness")
    try {
      const health = await request("/global/health", undefined, 5000)
      assert.equal(health.value.healthy, true)
      ready = true
      break
    } catch (error) {
      attempts.push(String(error))
      await Bun.sleep(250)
    }
  }
  lifecycle.healthAttempts = attempts
  timings.healthStartupMs = performance.now() - startup
  assert(ready, "Host health readiness deadline")
  console.log(JSON.stringify({ stage:"host_ready", hostURL, pid:host.pid }))

  const catalog = await request("/provider")
  assertMetadata("/provider", catalog, catalog.value.all)
  const configured = await request("/config/providers")
  assertMetadata("/config/providers", configured, configured.value.providers)
  assert(catalog.value.connected.includes("fixture"))
  console.log(JSON.stringify({ stage:"metadata_boundary_passed" }))

  const session = (await request("/session", { title:"Provider metadata and private runtime fixture" })).value
  client = Bun.spawn({
    cmd:[process.execPath,"run","--conditions=browser",launcher,"run","--attach",hostURL,
      "--dir",fixture.workspace,"--pure","--auto","--format","json",
      "--session",session.id,"--model","fixture/fixture-reasoner","--variant","high",...(planned ? ["--hackathon"] : []),fixture.goal],
    cwd, env:fixture.env, stdin:"ignore", stdout:"pipe", stderr:"pipe",
  })
  lifecycle.clientPID = client.pid
  clientStreams = { stdout:new Response(client.stdout).text(), stderr:new Response(client.stderr).text() }
  const started = performance.now()
  lifecycle.clientExitCode = await client.exited
  timings.clientMs = performance.now() - started
  assert(!timedOut, "Overall provider boundary diagnostic deadline")
  finalStatus = (await request("/session/" + session.id + "/harness")).value
  if (failIntegration) {
    assert.equal(lifecycle.clientExitCode, 1, "Provider failure must produce a non-success headless exit")
    assert.equal(finalStatus.phase, "blocked")
    assert.equal(finalStatus.outcome, "blocked")
    assert.equal(finalStatus.readyEligible, false)
    assert.equal(finalStatus.failureKind, "model_provider_error")
    assert.equal(finalStatus.repairCount, 0, "Provider failure must not trigger implementation repair")
    assert(finalStatus.workers.every(worker => worker.repairCount === 0))
    assert.equal(fixture.requestLog.filter(request => request.rootIntegration).length, 1,
      "Non-retryable integration error must not repeat the provider call")
    assert.equal(fixture.requestLog.filter(request => request.selected === "harness_contract").length, 1)
    assert.equal(fixture.requestLog.filter(request => request.selected === "harness_workgraph").length, 1)
  } else if (exhaustWorker) {
    assert.equal(lifecycle.clientExitCode, 1, "Exhausted required work must produce a non-success exit")
    assert.equal(finalStatus.phase, "blocked")
    assert.equal(finalStatus.outcome, "blocked")
    assert.equal(finalStatus.readyEligible, false)
    assert.equal(finalStatus.failureKind, "implementation_error")
  } else {
    assert.equal(lifecycle.clientExitCode, 0, "Headless authenticated fixture must complete")
    assert.equal(finalStatus.phase, "ready")
    assert.equal(finalStatus.outcome, "ready")
    assert.equal(finalStatus.readyEligible, true)
  }
  for (const target of (exhaustWorker ? fixture.targets.slice(1) : fixture.targets)) assert.equal(await readFile(target,"utf8"), fixture.expected)
  assert(fixture.requestLog.length > 0)
  assert(fixture.requestLog.every(request => request.authenticated), "Host must retain its real fixture credential")
  assert(fixture.requestLog.some(request => request.reasoningEffort === "high"), "Private native effort payload must still reach the provider")

  if (planned) {
    const workers = fixture.requestLog.filter(request => request.workUnitId !== undefined)
    assert.equal(new Set(workers.map(request => request.workUnitId)).size, fixture.targets.length, "All WorkUnits must reach the provider")
    const allowed = new Set(["read","glob","grep","edit","write","lsp","question","invalid"])
    assert(workers.every(request => request.tools.every(id => allowed.has(id))), "Worker catalog contains a forbidden tool")
    assert(workers.every(request => request.tools.includes("write") || request.tools.includes("edit")), "Worker has no structured editor")
    assert.equal(finalStatus.workers.filter(worker => worker.state === "completed").length, 2)
    checks.push({scope:"worker_catalog",workUnits:fixture.targets.length,forbiddenToolsAdvertised:false,structuredEditorsAvailable:true})
  }

  if (repairWorker) {
    const repaired = finalStatus.workers.find(worker => worker.workUnitId === "unit-0")
    const untouched = finalStatus.workers.find(worker => worker.workUnitId === "unit-1")
    assert(repaired && untouched, "Both planned workers must be represented")
    assert.equal(repaired.state, "completed")
    assert.equal(repaired.repairCount, 1)
    assert.equal(untouched.repairCount, 0)
    const writes = fixture.requestLog.filter(request => request.selected === "write")
    const repairedWrites = writes.filter(request => request.workUnitId === "unit-0")
    assert.equal(repairedWrites.length, 2)
    assert.equal(repairedWrites[0].injectedIncorrectContent, true)
    assert.equal(repairedWrites[1].injectedIncorrectContent, false)
    assert.equal(repairedWrites[1].workspaceBeforeRepair, null, "Rejected candidate leaked into the base workspace")
    assert.equal(writes.filter(request => request.workUnitId === "unit-1").length, 1)
    assert.equal(fixture.requestLog.filter(request => request.selected === "harness_contract").length, 1)
    assert.equal(fixture.requestLog.filter(request => request.selected === "harness_workgraph").length, 1)
    assert(fixture.requestLog.filter(request => request.workUnitId).every(request =>
      request.model === "fixture-reasoner" && request.reasoningEffort === "high"))
    // Read the actual child session, not a fixture-inferred session identifier.
    const messages = (await request("/session/" + repaired.scopeId + "/message")).value
    assert(Array.isArray(messages), "Child message API must return an array")
    assert(messages.length <= 50, "Unexpected fixture child history size")
    const recordedWrites = messages.flatMap(message => {
      assert.equal(message.info.sessionID, repaired.scopeId)
      return message.parts.filter(part => part.type === "tool" && part.tool === "write")
    })
    assert.equal(recordedWrites.length, 2, "Initial write and repair must be in the same child session")
    assert(recordedWrites.every(part => part.state.status === "completed"))
    assert.equal(recordedWrites[0].state.input.content, "fixture incorrect\n")
    assert.equal(recordedWrites[1].state.input.content, fixture.expected)
    const stored = await inspectRootReadyArtifacts(finalStatus.runId, session.id)
    assert.equal(stored.readyArtifacts.length, 1, "Expected exactly one stored root Ready")
    const ready = stored.readyArtifacts[0].payload
    const selected = ready.claimResults.flatMap(claim => (claim.familyIds ?? []).map(familyId => {
      const family = ready.evidenceFamilies.find(item => item.familyId === familyId && item.claimId === claim.claimId)
      assert(family, "Ready selects an unrepresented claim-family")
      assert.equal(family.status, "active")
      assert.equal(family.statusScope, "verification_observation")
      assert(claim.evidenceIds.every(id => family.evidenceIds.includes(id)))
      return family
    }))
    assert(selected.some(family => family.claimId === "claim-0" && family.memoryCaseStatus === "disputed"),
      "Repair must preserve the historical soft-failure warning")
    checks.push({ scope:"ready_family_consistency", selectedFamiliesActive:true,
      historicalDisputePreserved:true, readyArtifact:stored.readyArtifacts[0].path })
    checks.push({ scope:"worker_local_repair", workUnitId:"unit-0", scopeId:repaired.scopeId,
      repairCount:1, sameSessionWriteCount:2, unaffectedWorkerWriteCount:1,
      baseWorkspaceAbsentBeforeRepair:true, model:"fixture-reasoner", exactEffort:"high", replanned:false })
  }

  if (exhaustWorker) {
    const exhausted = finalStatus.workers.find(worker => worker.workUnitId === "unit-0")
    assert(exhausted, "Failed WorkUnit is missing")
    assert.equal(exhausted.state, "repair_exhausted")
    assert.equal(exhausted.repairCount, 2)
    assert(finalStatus.workers.filter(worker => worker.workUnitId !== "unit-0").every(worker =>
      worker.state === "completed" && worker.repairCount === 0))
    const writes = fixture.requestLog.filter(request => request.selected === "write")
    const attempts = writes.filter(request => request.workUnitId === "unit-0")
    assert.equal(attempts.length, 3, "Initial attempt plus exactly two repairs are allowed")
    assert(attempts.every(request => request.injectedIncorrectContent === true))
    assert(attempts.slice(1).every(request => request.workspaceBeforeRepair === null))
    for (const unit of ["unit-1", "unit-2"]) assert.equal(writes.filter(request => request.workUnitId === unit).length, 1)
    await assert.rejects(readFile(fixture.targets[0], "utf8"), error => error.code === "ENOENT")
    assert.equal(fixture.requestLog.filter(request => request.rootIntegration).length, 0)
    assert.equal(fixture.requestLog.filter(request => request.selected === "harness_contract").length, 1)
    assert.equal(fixture.requestLog.filter(request => request.selected === "harness_workgraph").length, 1)
    assert(fixture.requestLog.filter(request => request.workUnitId).every(request =>
      request.model === "fixture-reasoner" && request.reasoningEffort === "high"))
    const messages = (await request("/session/" + exhausted.scopeId + "/message")).value
    assert(Array.isArray(messages) && messages.length <= 50)
    const recordedWrites = messages.flatMap(message => {
      assert.equal(message.info.sessionID, exhausted.scopeId)
      return message.parts.filter(part => part.type === "tool" && part.tool === "write")
    })
    assert.equal(recordedWrites.length, 3)
    assert(recordedWrites.every(part => part.state.status === "completed" && part.state.input.content === "fixture incorrect\n"))
    const stored = await inspectRootReadyArtifacts(finalStatus.runId, session.id)
    assert.equal(stored.readyArtifacts.length, 0)
    assert.equal(stored.scopeAttestations.filter(item => item.payload.scopeId === exhausted.scopeId).length, 0)
    const rejected = stored.rejections.filter(item => item.payload.repairScopeId === exhausted.scopeId)
      .sort((a,b) => a.payload.rejectionCount - b.payload.rejectionCount)
    assert.deepEqual(rejected.map(item => item.payload.rejectionCount), [1,2,3])
    assert.deepEqual(rejected.map(item => item.payload.outcome), ["repair","repair","repair_exhausted"])
    assert.equal(new Set(rejected.map(item => item.payload.failureFingerprint)).size, 1)
    assert.equal(rejected[2].payload.failureFingerprint, exhausted.failureFingerprint)
    const queuedStart = fixture.requestLog.find(request => request.workUnitId === "unit-2").receivedAt
    const exhaustedAt = Date.parse(rejected[2].createdAt)
    assert(Number.isFinite(exhaustedAt) && queuedStart >= exhaustedAt,
      "The queued independent unit must start after the failed scope exhausted its repairs")
    assert(fixture.exhaustionBarrier.heldAt < exhaustedAt)
    assert(fixture.exhaustionBarrier.releasedAt >= exhaustedAt)
    checks.push({ scope:"repair_exhaustion", workUnitId:"unit-0", scopeId:exhausted.scopeId,
      attempts:3, automaticRepairs:2, oneFingerprint:true, sameSessionWriteCount:3,
      rejectedCandidateCommitted:false, storedRootReadyCount:0, unrelatedCompletedUnits:["unit-1","unit-2"],
      queuedStart, exhaustedAt, barrier:fixture.exhaustionBarrier,
      rejections:rejected.map(item => ({path:item.path,...item.payload})), replanned:false })
  }

  const signedState = JSON.parse(await readFile(path.join(fixture.state,"base-harness","sessions",session.id+".json"),"utf8"))
  assert.equal(signedState.body.lastRun.runId, finalStatus.runId)
  assert.equal(signedState.body.lastRun.phase, failIntegration || exhaustWorker ? "blocked" : "ready")
  assert.equal(signedState.body.lastRun.revalidated, false)
  if (failIntegration) {
    // Inspect primary storage too: a false UI status alone does not prove no Ready was issued.
    const { readyArtifacts, entriesVisited, jsonFilesRead, runArtifacts } =
      await inspectRootReadyArtifacts(finalStatus.runId, session.id)
    const rootReadyArtifacts = readyArtifacts.map(item => item.path)
    assert.equal(rootReadyArtifacts.length, 0, "Failed root must not have a persisted Ready attestation")
    checks.push({ scope:"integration_provider_failure", expectedClientExit:1,
      failureKind:finalStatus.failureKind, implementationRepairs:0, replanned:false,
      completedFilesPreserved:true, rootReadyArtifacts, entriesVisited, jsonFilesRead, runArtifacts })
  }
  checks.push({ scope:"private_runtime", authenticated:true, exactEffort:"high", fileMatches:!exhaustWorker, retainedFilesMatch:true, currentRootReady:!failIntegration && !exhaustWorker })
  console.log(JSON.stringify({ stage:"authenticated_execution_passed", sessionID:session.id, runId:finalStatus.runId }))
} catch (error) {
  failure = error instanceof Error ? error.stack ?? error.message : String(error)
} finally {
  clearTimeout(deadline)
  if (client?.exitCode === null) client.kill()
  if (client) {
    lifecycle.clientExitCode = await client.exited
    await writeFile(path.join(logRoot,tag+"-client.stdout.log"),await clientStreams.stdout)
    await writeFile(path.join(logRoot,tag+"-client.stderr.log"),await clientStreams.stderr)
  }
  if (host?.exitCode === null) host.kill()
  if (host) {
    lifecycle.hostExitCode = await host.exited
    await writeFile(path.join(logRoot,tag+"-host.stdout.log"),await hostStreams.stdout)
    await writeFile(path.join(logRoot,tag+"-host.stderr.log"),await hostStreams.stderr)
  }
  fixture.stop()
}
const result = {
  diagnosticOnly:true,success:!failure,scope:"Local deterministic provider HTTP metadata and authenticated private Host execution, not OAuth or user reliability",
  scratch:fixture.scratch,workspace:fixture.workspace,state:fixture.state,checks,timings,lifecycle,
  planned,failIntegration,repairWorker,exhaustWorker,finalStatus,modelRequests:fixture.requestLog,timedOut,failure,
}
const resultPath = path.join(logRoot,tag+".result.json")
await writeFile(resultPath,JSON.stringify(result,null,2))
console.log(JSON.stringify({ success:result.success,resultPath,failure }))
if (failure) process.exitCode = 1
