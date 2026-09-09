import { expect, test } from "bun:test"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, relative } from "node:path"
import { createVerificationClient, type CandidateManifest, type OpenRunInput } from "@base-harness/verification"
import { CoordinatorRuntime } from "../src"

for (const tamper of [false, true]) {
  test("real Python candidate verification " + (tamper ? "rejects staged tampering without commit" : "attests Unicode file hashes before commit"), async () => {
    const directory = await mkdtemp(join(tmpdir(), "harness-real-candidate-"))
    const workspace = join(directory, "workspace")
    const state = join(directory, "state")
    await mkdir(workspace)
    await mkdir(state)
    const names = ["z.txt", "\u00e9.txt"]
    for (const name of names) await writeFile(join(workspace, name), "before")
    const environmentKeys = ["APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"]
    const previous = new Map(environmentKeys.map(key => [key, process.env[key]]))
    for (const key of environmentKeys) process.env[key] = state
    const order: string[] = []
    const factory = async (input: OpenRunInput) => {
      const client = await createVerificationClient(input, {
        command: [process.env.BASE_HARNESS_PYTHON ?? "python", "-m", "harness.verified_sidecar"],
        cwd: workspace, env: { ...process.env }, timeoutMs: 10000,
      })
      const candidates = new Map<string, CandidateManifest>()
      const attach = client.attachCandidate.bind(client)
      client.attachCandidate = async candidate => {
        candidates.set(candidate.scopeId, candidate)
        return attach(candidate)
      }
      const verify = client.verify.bind(client)
      client.verify = async (reason, scopeId, target) => {
        const candidate = scopeId ? candidates.get(scopeId) : undefined
        if (tamper && candidate) await writeFile(join(candidate.candidateWorkspace!, names[0]!), "tampered")
        const result = await verify(reason, scopeId, target)
        if (candidate && result.outcome === "scope_verified") {
          for (const name of names) expect(await readFile(join(workspace, name), "utf8")).toBe("before")
          order.push("scope_verified")
        }
        return result
      }
      const commit = client.commitCandidate.bind(client)
      client.commitCandidate = async (attestation, scopeId) => {
        for (const name of names) expect(await readFile(join(workspace, name), "utf8")).toBe("after")
        const result = await commit(attestation, scopeId)
        order.push("commit_ack")
        return result
      }
      return client
    }
    const runtime = new CoordinatorRuntime(factory)
    try {
      runtime.orchestration.beginPrompt({
        sessionID: "root", workspace, goal: "Write after to both requested files", exploration: "manual",
      })
      await runtime.openRun({ sessionID: "root", workspace, goal: "Write after to both requested files", trigger: "manual" })
      await runtime.proposeContract("root", {
        goal: "Write after to both requested files",
        criteria: [{ criterionId: "criterion", statement: "Both files contain after", claimIds: ["claim"], required: true, risk: "low" }],
        claims: [{
          claimId: "claim", criterionIds: ["criterion"], origin: "user", statement: "Both files contain after", kind: "artifact",
          scope: { targets: names, capabilities: ["write"], exclusions: [] },
          predicate: { type: "content_equals", value: "after" },
          verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
        }],
      })
      runtime.orchestration.beginPlanning("root")
      runtime.registerIntegrationExecutor(async () => undefined)
      runtime.registerWorkerExecutor(async ({ rootSessionID, unit }) => {
        runtime.orchestration.startChild({ parentSessionID: rootSessionID, sessionID: "worker", subagentType: "general", workUnitId: unit.id })
        for (const name of names) {
          const route = await runtime.orchestration.resolveWrite("worker", workspace, name)
          await writeFile(route.physicalPath, "after")
        }
        await runtime.finishWorker("worker", true)
        return { sessionID: "worker" }
      })
      await runtime.acceptWorkGraph("root", {
        units: [{ id: "unit", title: "Both files", instructions: "Write after", claimIds: ["claim"], criterionIds: ["criterion"],
          dependsOn: [], readSet: names, writeSet: names, integrationRequests: [] }],
        integrationPaths: [],
      }, {})
      const result = await runtime.verifyRoot("root", "completion")
      if (tamper) {
        expect(result.workers[0]?.state).toBe("failed")
        expect(result.failureKind).toBe("workspace_conflict")
        expect(result.readyEligible).toBe(false)
        expect(result.evidenceCount).toBe(0)
        expect(order).toEqual([])
        for (const name of names) expect(await readFile(join(workspace, name), "utf8")).toBe("before")
      } else {
        expect(result.outcome).toBe("ready")
        expect(result.workers[0]?.state).toBe("completed")
        expect(result.evidenceRefs.every(ref => ref !== "[object Object]" && ref.endsWith(".json"))).toBe(true)
        expect(order).toEqual(["scope_verified", "commit_ack"])
      }
    } finally {
      await runtime.closeWorkspace(workspace)
      runtime.resetForTest()
      for (const [key, value] of previous) {
        if (value === undefined) delete process.env[key]
        else process.env[key] = value
      }
      expect(relative(tmpdir(), directory).startsWith("..")).toBe(false)
      await rm(directory, { recursive: true, force: true })
    }
  }, 20000)
}
