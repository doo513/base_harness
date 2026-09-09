/**
 * Real Host -> local model HTTP -> stdio MCP -> Python verifier smoke test.
 * No paid model, external account, or mock VerificationClient is used.
 */
import { mkdir, writeFile, readFile, readdir } from "node:fs/promises"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime"
import path from "node:path"
import { fileURLToPath } from "node:url"

const runtime = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const repo = path.dirname(runtime)
const python = process.env.BASE_HARNESS_PYTHON
if (!python) throw new Error("BASE_HARNESS_PYTHON must identify the installed verifier interpreter")
const planned = process.argv.includes("--planned")
const failIntegration = process.argv.includes("--fail-integration")
if (failIntegration && !planned) throw new Error("--fail-integration requires --planned")
const fixture = await createLocalRuntimeFixture(python, { planned, failIntegration })
const { scratch, workspace, state, targets, criterionIds, claimIds, expected, marker, goal, requestLog } = fixture
const artifactPrefix = failIntegration ? "real-host-integration-failure-flow" : planned ? "real-host-planned-flow" : "real-host-flow"

let timedOut = false
const child = Bun.spawn({
  cmd: [
    process.execPath, "run", "--conditions=browser",
    path.join(runtime, "packages/base-harness/src/source-launcher.ts"),
    "run", "--dir", workspace, "--format", "json",
    "--model", "fixture/fixture-model", "--pure", "--auto", goal,
  ],
  cwd: path.join(runtime, "packages/base-harness"),
  env: {
    ...process.env,
    BASE_HARNESS_PYTHON: python, BASE_HARNESS_LAUNCH_CWD: workspace,
    BASE_HARNESS_DISABLE_MODELS_FETCH: "true",
    APPDATA: state, LOCALAPPDATA: state,
    XDG_CONFIG_HOME: state, XDG_DATA_HOME: state, XDG_STATE_HOME: state, XDG_CACHE_HOME: state,
  },
  stdin: "ignore", stdout: "pipe", stderr: "pipe",
})
const timeout = setTimeout(() => { timedOut = true; child.kill() }, 120_000)
async function collect(stream: ReadableStream<Uint8Array>) {
  const decoder = new TextDecoder()
  let text = ""
  let count = 0
  for await (const chunk of stream) {
    count += chunk.length
    if (count > 10 * 1024 * 1024) {
      child.kill()
      throw new Error("Host fixture output exceeded 10 MiB")
    }
    text += decoder.decode(chunk, { stream: true })
  }
  return text + decoder.decode()
}

let stdout = ""
let stderr = ""
let exitCode = -1
try {
  const out = collect(child.stdout)
  const err = collect(child.stderr)
  exitCode = await child.exited
  stdout = await out
  stderr = await err
} finally {
  clearTimeout(timeout)
  fixture.stop()
}

const logs = path.join(repo, ".tools/validation")
await mkdir(logs, { recursive: true })
await writeFile(path.join(logs, artifactPrefix + ".stdout.jsonl"), stdout)
await writeFile(path.join(logs, artifactPrefix + ".stderr.log"), stderr)

const artifactTexts = await Promise.all(targets.map(target => readFile(target, "utf8").catch(() => null)))
const artifactMatches = artifactTexts.every(text => text === expected)
const mcpCalls = await readFile(marker, "utf8").catch(() => "")
const ready: Array<{ path: string; value: any }> = []
let visited = 0
async function findReady(directory: string): Promise<void> {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    if (++visited > 4096) throw new Error("Fixture state inspection exceeded its bound")
    const filename = path.join(directory, entry.name)
    if (entry.isDirectory()) await findReady(filename)
    else if (entry.isFile() && entry.name.endsWith(".json")) {
      const value = await readFile(filename, "utf8").then(JSON.parse).catch(() => null)
      if (value?.artifactType === "ready_attestation" || value?.kind === "ready_attestation"
          || (value?.trust === "verifier_attested" && value?.payload?.criterionResults && value?.payload?.evidenceRefs)) {
        ready.push({ path: filename, value })
      }
    }
  }
}
await findReady(state)
const verifiedReady = ready.find(({ value }) => {
  const payload = value.payload ?? value
  return criterionIds.every(id => payload.criterionResults?.some((item: any) => item.criterionId === id && item.result === "verified"))
    && claimIds.every(id => payload.claimResults?.some((item: any) => item.claimId === id && item.result === "verified"))
    && payload.evidenceRefs?.length > 0
})
const selected = requestLog.flatMap((request) => request.selected ? [request.selected] : [])
const integrationObserved = requestLog.some(request => request.rootIntegration)
const plannedFlowObserved = !planned || (
  integrationObserved &&
  selected.includes("harness_workgraph")
  && requestLog.some(request => request.reviewPhase === "goal_contract")
  && requestLog.some(request => request.reviewPhase === "plan")
  && targets.every((_, index) => requestLog.some(request => request.workUnitId === "unit-" + index && request.selected === "write"))
)
const completionMatches = failIntegration
  ? exitCode !== 0 && !verifiedReady && integrationObserved
  : exitCode === 0 && !!verifiedReady
const success = completionMatches && !timedOut && artifactMatches && plannedFlowObserved
  && mcpCalls.includes('"name": "echo"')
  && requestLog.some((request) => request.authenticated && request.model === "fixture-model")
  && selected.includes("harness_contract") && selected.includes("write")
const summary = {
  success, planned, expectedIntegrationFailure: failIntegration, integrationObserved,
  plannedFlowObserved, scratch, exitCode, timedOut, modelRequests: requestLog.length,
  toolRequests: selected, mcpCalls: mcpCalls.trim().split("\n").filter(Boolean).length,
  artifactMatches, verifiedCriterionCount: criterionIds.length, readyArtifact: verifiedReady?.path,
  requests: requestLog,
  failureOutput: success ? undefined : { stdout: stdout.slice(-12000), stderr: stderr.slice(-12000) },
}
await writeFile(path.join(logs, artifactPrefix + ".result.json"), JSON.stringify(summary, null, 2))
console.log(JSON.stringify(summary, null, 2))
if (!success) process.exitCode = 1
