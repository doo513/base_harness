import { expect, test } from "bun:test"
import { mkdtemp, mkdir, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { CoordinatorRuntime, RunRepository } from "../../coordinator/src"
import { createVerificationClient } from "../../verification/src"
import { KernelHost } from "../src"
import { contractFixture } from "./contract-fixture"

for (const allowed of [true, false]) test(`real Python verifier ${allowed ? "accepts" : "rejects"} the checked contract without Evidence or Ready`, async () => {
  const directory = await mkdtemp(join(tmpdir(), "contract-verifier-")), workspace = join(directory, "workspace"), state = join(directory, "state")
  await mkdir(workspace); await mkdir(state)
  const keys = ["APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"]
  const previous = new Map(keys.map((key) => [key, process.env[key]]))
  for (const key of keys) process.env[key] = state
  let verificationCalls = 0, launches = 0
  const runtime = new CoordinatorRuntime(async (input) => {
    launches++
    const client = await createVerificationClient(input, {
      command: [process.env.BASE_HARNESS_PYTHON ?? "python3", "-m", "harness.verified_sidecar"], cwd: workspace,
      env: { ...process.env, PYTHONPATH: resolve(import.meta.dir, "../../../../src") }, timeoutMs: 10000,
    })
    const verify = client.verify.bind(client)
    client.verify = (...args) => { verificationCalls++; return verify(...args) }
    return client
  }, { repository: new RunRepository({ stateDirectory: join(state, "coordinator") }) })
  const host = new KernelHost(runtime, { directory: join(state, "plans") })
  runtime.registerCompletionGate((sessionID) => host.canVerifyRoot(sessionID))
  try {
    await host.openRun({ sessionID: "root", workspace, goal: "A file must exist", trigger: "manual" })
    const candidate = contractFixture({
      goal: "A file must exist", criteria: [{ criterionId: "k", claimIds: ["c"] }],
      claims: [{ claimId: "c", criterionIds: ["k"], applicability: { os: "any" },
        verifierPolicy: { allowedVerifierIds: [allowed ? "file" : "unknown-verifier"] } }],
    })
    if (allowed) {
      const result = await host.proposeContract("root", candidate)
      expect(result.contractStatus).toBe("accepted")
      expect(host.hasAcceptedContract("root")).toBe(true)
    } else {
      await expect(host.proposeContract("root", candidate)).rejects.toThrow()
      expect(host.hasAcceptedContract("root")).toBe(false)
      expect(() => host.assertToolAllowed("root", "write")).toThrow()
    }
    const status = host.status("root")
    expect(launches).toBe(1)
    expect(verificationCalls).toBe(0)
    expect(status.evidenceCount).toBe(0)
    expect(status.readyEligible).toBe(false)
    expect(status.outcome).not.toBe("ready")
  } finally {
    await runtime.closeWorkspace(workspace); runtime.resetForTest()
    for (const [key, value] of previous) { if (value === undefined) delete process.env[key]; else process.env[key] = value }
    await rm(directory, { recursive: true, force: true })
  }
}, 30000)
