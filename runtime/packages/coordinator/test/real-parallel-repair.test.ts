import { expect, test } from "bun:test"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import { createVerificationClient, VerificationClientError, type OpenRunInput } from "@base-harness/verification"
import { OrchestrationError } from "@base-harness/workspace/orchestration"
import { CoordinatorRuntime } from "../src"

for (const scenario of [
  "parallel", "repair", "exhausted", "dependent-exhausted", "provider-failure",
  "reopen-failure", "unverified-return", "workspace-error", "setup-error", "root-provider-failure",
  "root-harness-failure", "missing-integration",
] as const) {
  test("real verifier coordinates independent workers: " + scenario, async () => {
    const directory = await mkdtemp(join(tmpdir(), "harness-real-parallel-"))
    const workspace = join(directory, "workspace"), state = join(directory, "state")
    await mkdir(workspace)
    await mkdir(state)
    const dependent = scenario === "dependent-exhausted"
    const exhausts = scenario === "exhausted" || dependent
    const earlyFailure = ["provider-failure", "unverified-return", "workspace-error", "setup-error"].includes(scenario)
    const ids = dependent ? ["a", "b", "c", "d"] : ["a", "b", "c"]
    const independent = ids.filter(id => id !== "a" && !(dependent && id === "c"))
    for (const id of ids) await writeFile(join(workspace, id + ".txt"), "before")
    const keys = ["APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"]
    const previous = new Map(keys.map(key => [key, process.env[key]]))
    for (const key of keys) process.env[key] = state
    const model = { providerID: "fixture", modelID: "fixture-model", variant: "max" }
    const context = { model }
    const attempts = new Map<string, number>()
    const sessions = new Map<string, string[]>()
    const revisions = new Map<string, number[]>()
    const order: Array<{ scope: string; event: string }> = []
    let active = 0, maximum = 0, rootVerificationCalls = 0
    const overlays = new Map<string, string>()
    let releaseSibling!: () => void
    const siblingGate = new Promise<void>(resolve => { releaseSibling = resolve })
    let releaseContinuationChecks!: () => void
    const continuationGate = new Promise<void>(resolve => { releaseContinuationChecks = resolve })
    const continuationChecks: Array<Promise<boolean>> = []
    const factory = async (input: OpenRunInput) => {
      const client = await createVerificationClient(input, {
        command: [process.env.BASE_HARNESS_PYTHON ?? "python", "-m", "harness.verified_sidecar"],
        cwd: workspace, env: { ...process.env }, timeoutMs: 10000,
      })
      if (scenario === "reopen-failure") {
        client.reopenScope = async () => {
          throw new VerificationClientError("harness_protocol_error", "injected repair reopen failure")
        }
      }
      const attach = client.attachCandidate.bind(client)
      client.attachCandidate = async candidate => {
        revisions.set(candidate.scopeId, [...(revisions.get(candidate.scopeId) ?? []), candidate.revision])
        return attach(candidate)
      }
      const verify = client.verify.bind(client)
      client.verify = async (reason, scope, target) => {
        if (scope === "root") rootVerificationCalls += 1
        const result = await verify(reason, scope, target)
        if (scope?.startsWith("worker-") && result.outcome === "scope_verified") {
          expect(await readFile(join(workspace, scope.slice("worker-".length) + ".txt"), "utf8")).toBe("before")
          order.push({ scope, event: "scope_verified" })
        }
        return result
      }
      const commit = client.commitCandidate.bind(client)
      client.commitCandidate = async (attestation, scope) => {
        expect(order.some(event => event.scope === scope && event.event === "scope_verified")).toBe(true)
        expect(await readFile(join(workspace, scope!.slice("worker-".length) + ".txt"), "utf8")).toBe("after")
        const result = await commit(attestation, scope)
        order.push({ scope: scope!, event: "commit_ack" })
        return result
      }
      return client
    }
    const runtime = new CoordinatorRuntime(factory)
    try {
      runtime.orchestration.beginPrompt({
        sessionID: "root", workspace, goal: "Write after to three independent files", exploration: "manual", model,
      })
      await runtime.openRun({ sessionID: "root", workspace, goal: "Write after to three independent files", trigger: "manual" })
      await runtime.proposeContract("root", {
        goal: "Write after to three independent files",
        criteria: ids.map(id => ({
          criterionId: "criterion-" + id, statement: "Write after to " + id + ".txt",
          claimIds: ["claim-" + id], required: true, risk: "low" as const,
        })),
        claims: ids.map(id => ({
          claimId: "claim-" + id, criterionIds: ["criterion-" + id], origin: "user" as const,
          statement: "Write after to " + id + ".txt", kind: "artifact" as const,
          scope: { targets: [id + ".txt"], capabilities: ["write"], exclusions: [] },
          predicate: { type: "content_equals", value: "after" },
          verifierPolicy: { minimumStrength: "structural" as const, allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
        })),
      })
      runtime.orchestration.beginPlanning("root")
      if (scenario !== "missing-integration") runtime.registerIntegrationExecutor(async () => {
        expect(runtime.isInternalContinuation("root")).toBe(true)
        expect(runtime.isInternalContinuation("worker-a")).toBe(false)
        continuationChecks.push(continuationGate.then(() => runtime.isInternalContinuation("root")))
        await Bun.sleep(1)
        expect(runtime.isInternalContinuation("root")).toBe(true)
        if (scenario === "root-harness-failure") throw Object.assign(new Error("Injected root model-selection mismatch"), { code: "HOST_MODEL_SELECTION_INVALID" })
        if (scenario !== "root-provider-failure") return
        await runtime.observe({
          type: "session.error",
          data: { sessionID: "root", error: { name: "LLMError", reason: { _tag: "Authentication" }, message: "Root provider authentication fixture failure." } },
        })
        throw new Error("Integration surfaced a generic display error after the typed provider failure.")
      })
      runtime.registerWorkerExecutor(async ({ rootSessionID, unit, taskID, context: inherited, repairPrompt }) => {
        expect(inherited).toBe(context)
        expect((inherited as typeof context).model).toEqual(model)
        const sessionID = taskID ?? "worker-" + unit.id
        sessions.set(unit.id, [...(sessions.get(unit.id) ?? []), sessionID])
        const attempt = (attempts.get(unit.id) ?? 0) + 1
        attempts.set(unit.id, attempt)
        if (attempt > 1) {
          expect(taskID).toBe("worker-" + unit.id)
          expect(repairPrompt).toContain("criterion-" + unit.id)
        }
        active += 1
        maximum = Math.max(maximum, active)
        try {
          runtime.orchestration.startChild({
            parentSessionID: rootSessionID, sessionID, subagentType: "general", workUnitId: unit.id, model,
          })
          runtime.registerWorkerScope(rootSessionID, sessionID, unit.id)
          const route = await runtime.orchestration.resolveWrite(sessionID, workspace, unit.id + ".txt")
          overlays.set(unit.id, route.physicalPath)
          if (scenario === "provider-failure" && unit.id === "b") await siblingGate
          await Bun.sleep(15)
          if (scenario === "provider-failure" && unit.id === "a") {
            await runtime.observe({
              type: "session.error",
              data: { sessionID, error: { name: "LLMError", reason: { _tag: "RateLimit" }, message: "Provider fixture denied this request." } },
            })
            await runtime.finishWorker(sessionID, false)
            throw new Error("Subagent failed after the original typed error was observed.")
          }
          const fail = unit.id === "a" && (exhausts || scenario === "reopen-failure" || (scenario === "repair" && attempt === 1))
          await writeFile(route.physicalPath, fail ? "wrong" : "after")
          if (unit.id === "a") {
            if (scenario === "unverified-return") return { sessionID }
            if (scenario === "workspace-error") throw new OrchestrationError("WORKSPACE_CONFLICT", "Injected workspace conflict")
            if (scenario === "setup-error") throw new Error("rate limit text inside a Host setup failure must not change its origin")
          }
          await runtime.finishWorker(sessionID, true)
        } finally {
          active -= 1
        }
        return { sessionID }
      })
      await runtime.acceptWorkGraph("root", {
        units: ids.map(id => ({
          id, title: id, instructions: "Write after to " + id + ".txt", claimIds: ["claim-" + id],
          criterionIds: ["criterion-" + id], dependsOn: dependent && id === "c" ? ["a"] : [], readSet: [id + ".txt"], writeSet: [id + ".txt"],
          integrationRequests: [],
        })), integrationPaths: [],
      }, context)
      if (scenario === "provider-failure") {
        try {
          const deadline = Date.now() + 7000
          while (Date.now() < deadline) {
            const workers = runtime.status("root").workers
            if (workers.find(w => w.workUnitId === "a")?.state === "failed" &&
                workers.find(w => w.workUnitId === "c")?.state === "completed") break
            await Bun.sleep(10)
          }
          const running = runtime.status("root")
          expect(running.workers.find(w => w.workUnitId === "a")?.state).toBe("failed")
          expect(running.workers.find(w => w.workUnitId === "c")?.state).toBe("completed")
          expect(running.phase).toBe("worker_running")
          expect(running.outcome).not.toBe("failure")
          expect(running.outcome).not.toBe("blocked")
          expect(running.failureKind).toBeUndefined()
          const sameRun = await runtime.openRun({ sessionID: "root", workspace, goal: "Write after to three independent files" })
          expect(sameRun.runId).toBe(running.runId)
          expect(sameRun.activeCount).toBe(1)
        } finally {
          releaseSibling()
        }
      }
      const result = await runtime.verifyRoot("root", "completion")
      expect(result.workers.every(worker => !("verification" in worker))).toBe(true)
      expect(runtime.isInternalContinuation("root")).toBe(false)
      releaseContinuationChecks()
      expect(await Promise.all(continuationChecks)).toEqual(continuationChecks.map(() => false))
      expect(maximum).toBe(2)
      for (const id of independent) {
        expect(attempts.get(id)).toBe(1)
        expect(result.workers.find(worker => worker.workUnitId === id)?.state).toBe("completed")
        expect(await readFile(join(workspace, id + ".txt"), "utf8")).toBe("after")
      }
      if (dependent) {
        expect(attempts.has("c")).toBe(false)
        expect(result.workers.find(worker => worker.workUnitId === "c")?.state).toBe("queued")
        expect(await readFile(join(workspace, "c.txt"), "utf8")).toBe("before")
      }
      const expectedAttempts = exhausts ? 3 : scenario === "repair" ? 2 : 1
      expect(attempts.get("a")).toBe(expectedAttempts)
      expect(new Set(sessions.get("a")).size).toBe(1)
      expect(revisions.get("worker-a")).toEqual(earlyFailure ? undefined : Array.from({ length: expectedAttempts }, (_, index) => index + 1))
      if (["root-provider-failure", "root-harness-failure", "missing-integration"].includes(scenario)) {
        expect(result.outcome).toBe("blocked")
        const expectedKind = scenario === "root-provider-failure" ? "model_provider_error" : "harness_error"
        expect(result.failureKind).toBe(expectedKind)
        expect(result.readyEligible).toBe(false)
        expect(result.workers.every(worker => worker.state === "completed")).toBe(true)
        expect(order.filter(event => event.event === "commit_ack")).toHaveLength(3)
        expect(await readFile(join(workspace, "a.txt"), "utf8")).toBe("after")
        expect(rootVerificationCalls).toBe(0)
        for (const reason of ["manual", "automatic", "completion"] as const) {
          const repeated = await runtime.verifyRoot("root", reason)
          expect(repeated.outcome).toBe("blocked")
          expect(repeated.failureKind).toBe(expectedKind)
          expect(repeated.readyEligible).toBe(false)
        }
        await runtime.observe({
          type: "message.part.updated",
          data: { part: {
            id: "read-after-integration-failure", sessionID: "root", type: "tool", tool: "read",
            state: { status: "completed", input: { filePath: join(workspace, "a.txt") }, output: "after" },
          } },
        })
        const afterRead = await runtime.verifyRoot("root", "manual")
        expect(afterRead.outcome).toBe("blocked")
        expect(afterRead.failureKind).toBe(expectedKind)
        expect(afterRead.readyEligible).toBe(false)
        expect(rootVerificationCalls).toBe(0)
      } else if (scenario !== "parallel" && scenario !== "repair") {
        expect(result.outcome).toBe("blocked")
        const kind = exhausts ? "implementation_error"
          : scenario === "provider-failure" ? "model_provider_error"
          : scenario === "reopen-failure" ? "verifier_error"
          : scenario === "workspace-error" ? "workspace_conflict" : "harness_error"
        expect(result.failureKind).toBe(kind)
        if (exhausts) expect(result.failedCriterion).toBe("criterion-a")
        expect(result.repairCount).toBe(exhausts ? 2 : 0)
        expect(result.readyEligible).toBe(false)
        expect(result.workers.find(worker => worker.workUnitId === "a")?.state).toBe(exhausts ? "repair_exhausted" : "failed")
        if (scenario === "reopen-failure") {
          expect(await readFile(overlays.get("a")!, "utf8")).toBe("wrong")
          expect(runtime.orchestration.snapshot("root")?.candidates.some(candidate => candidate.scopeId === "worker-a")).toBe(true)
        }
        expect(order.some(event => event.scope === "worker-a" && event.event === "commit_ack")).toBe(false)
        expect(await readFile(join(workspace, "a.txt"), "utf8")).toBe("before")
      } else {
        expect(result.outcome).toBe("ready")
        expect(result.workers.every(worker => worker.state === "completed")).toBe(true)
        expect(order.filter(event => event.event === "commit_ack")).toHaveLength(3)
        expect(await readFile(join(workspace, "a.txt"), "utf8")).toBe("after")
      }
    } finally {
      releaseContinuationChecks()
      releaseSibling()
      await runtime.closeWorkspace(workspace)
      runtime.resetForTest()
      for (const [key, value] of previous) {
        if (value === undefined) delete process.env[key]
        else process.env[key] = value
      }
      const rel = relative(tmpdir(), directory)
      expect(rel.startsWith("..") || isAbsolute(rel)).toBe(false)
      await rm(directory, { recursive: true, force: true })
    }
  }, 30000)
}
