import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { createLocalRuntimeFixture } from "./fixtures/local-runtime"

const runtime = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const repo = path.dirname(runtime)
const python = process.env.BASE_HARNESS_PYTHON
if (!python) throw new Error("BASE_HARNESS_PYTHON is required")
const planned = process.argv.includes("--planned")
const failIntegration = process.argv.includes("--fail-integration")
if (failIntegration && !planned) throw new Error("--fail-integration requires --planned")
const fixture = await createLocalRuntimeFixture(python, { interactive: true, planned, failIntegration })
const portProbe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response("Reserved", { status: 503 }) })
const port = portProbe.port
portProbe.stop(true)
const hostURL = "http://127.0.0.1:" + port
const host = Bun.spawn({
  cmd: [
    process.execPath, "run", "--conditions=browser",
    path.join(runtime, "packages/base-harness/src/source-launcher.ts"),
    "serve", "--hostname", "127.0.0.1", "--port", String(port),
  ],
  cwd: path.join(runtime, "packages/base-harness"), env: fixture.env,
  stdin: "ignore", stdout: "pipe", stderr: "pipe",
})
const logs = path.join(repo, ".tools/validation")
await mkdir(logs, { recursive: true })
const out = new Response(host.stdout).text()
const err = new Response(host.stderr).text()
let stopping: Promise<void> | undefined
let lifetime: ReturnType<typeof setTimeout> | undefined
function stop() {
  if (stopping) return stopping
  stopping = (async () => {
    if (lifetime) clearTimeout(lifetime)
    if (host.exitCode === null) host.kill()
    await host.exited
    await writeFile(path.join(logs, "tui-fixture-host.stdout.log"), await out)
    await writeFile(path.join(logs, "tui-fixture-host.stderr.log"), await err)
    fixture.stop()
  })()
  return stopping
}
fixture.onStop(stop)
process.once("SIGINT", () => { void stop() })
process.once("SIGTERM", () => { void stop() })

try {
  let providers: any
  for (let attempt = 0; attempt < 80; attempt++) {
    if (host.exitCode !== null) throw new Error("Host exited during fixture startup")
    const response = await fetch(hostURL + "/provider?directory=" + encodeURIComponent(fixture.workspace), {
      signal: AbortSignal.timeout(1_000),
    }).catch(() => undefined)
    if (response?.ok) { providers = await response.json(); break }
    await Bun.sleep(500)
  }
  if (!providers) throw new Error("Host provider API did not become available")
  const metadata = {
    hostURL, modelURL: fixture.modelURL, workspace: fixture.workspace, state: fixture.state, planned, failIntegration,
    targets: fixture.targets, expected: fixture.expected, criterionIds: fixture.criterionIds, claimIds: fixture.claimIds,
    scratch: fixture.scratch, requestsPath: fixture.requestsPath, marker: fixture.marker,
    goal: fixture.goal, hostPID: host.pid, fixturePID: process.pid,
    fixtureCredential: fixture.token,
    providers: providers.all?.map((provider: any) => ({
      id: provider.id,
      models: Object.values(provider.models ?? {}).map((model: any) => ({
        id: model.id, reasoningEfforts: model.capabilities?.reasoningEfforts,
        variants: Object.keys(model.variants ?? {}),
      })),
    })),
  }
  await writeFile(path.join(logs, "tui-fixture-active.json"), JSON.stringify(metadata, null, 2))
  console.log(JSON.stringify(metadata, null, 2))
  lifetime = setTimeout(() => { void stop() }, 15 * 60_000)
} catch (error) {
  await stop()
  throw error
}
