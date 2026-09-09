import { expect, test } from "bun:test"
import { createHash } from "node:crypto"
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import { createVerificationClient, type GoalContractProposal, type OpenRunInput } from "@base-harness/verification"
import { CoordinatorRuntime, RunRepository } from "../src"

for (const scenario of ["accepted", "contract-rejected", "dispatch-error", "revised"] as const) {
  const rejectExecution = scenario === "contract-rejected"
  const expected = scenario === "revised" ? "revised after" : "after"
  test("a planned execution uses a new independent verifier run: " + scenario, async () => {
    const directory = await mkdtemp(join(tmpdir(), "harness-plan-execution-"))
    const workspace = join(directory, "workspace"), state = join(directory, "state")
    const stateDirectory = join(state, "coordinator")
    await mkdir(workspace)
    await mkdir(state)
    await writeFile(join(workspace, "input.ts"), "before")
    const keys = ["APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME"]
    const previous = new Map(keys.map(key => [key, process.env[key]]))
    for (const key of keys) process.env[key] = state
    const opened: OpenRunInput[] = []
    let verificationCalls = 0
    const factory = async (input: OpenRunInput) => {
      opened.push(input)
      const client = await createVerificationClient(input, {
        command: [process.env.BASE_HARNESS_PYTHON ?? "python", "-m", "harness.verified_sidecar"],
        cwd: workspace, env: { ...process.env }, timeoutMs: 10000,
      })
      const verify = client.verify.bind(client)
      client.verify = (...args) => { verificationCalls++; return verify(...args) }
      if (rejectExecution && opened.length === 2) {
        const propose = client.proposeContract.bind(client)
        client.proposeContract = async contract => ({
          ...await propose(contract), contractStatus: "missing", state: "blocked",
          outcome: "blocked", readyEligible: false, readyRef: null,
        })
      }
      return client
    }
    const runtime = new CoordinatorRuntime(factory, {
      repository: new RunRepository<any>({ stateDirectory }),
    })
    let contract: GoalContractProposal = {
      goal: "Change input.ts",
      criteria: [{ criterionId: "criterion", statement: "Write after", claimIds: ["claim"], required: true, risk: "low" }],
      claims: [{
        claimId: "claim", criterionIds: ["criterion"], origin: "user", statement: "Write after", kind: "artifact",
        scope: { targets: ["input.ts"], capabilities: ["write"], exclusions: [] },
        predicate: { type: "content_equals", value: "after" },
        verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
      }],
    }
    try {
      let planning = await runtime.openRun({
        sessionID: "root", workspace, goal: contract.goal, configuredProfile: "adaptive", trigger: "manual",
      })
      await runtime.proposeContract("root", contract)
      runtime.beginPlanning("root")
      await runtime.observe({
        type: "message.part.updated",
        data: { part: { id: "planning-read", sessionID: "root", type: "tool", tool: "read",
          state: { status: "completed", input: { filePath: "input.ts" }, output: "before" } } },
      })
      expect(runtime.status("root").metrics.observedActions).toBe(1)
      if (scenario === "revised") {
        const previousPlan = planning
        const revision = {
          planningRunId: planning.runId, planId: "reviewed-plan", planRevision: 1,
          goalContractHash: createHash("sha256").update(JSON.stringify(contract)).digest("hex"),
        }
        const nextGoal = "Change input.ts to revised after instead of after"
        for (const invalid of [
          { ...revision, planningRunId: "other-run" },
          { ...revision, goalContractHash: "0".repeat(64) },
        ]) {
          await expect(runtime.openRun({ sessionID: "root", workspace, goal: nextGoal, revisesPlan: invalid }))
            .rejects.toThrow()
          expect(runtime.status("root").runId).toBe(previousPlan.runId)
          expect(opened).toHaveLength(1)
        }
        const request = {
          sessionID: "root", workspace, goal: nextGoal, revisesPlan: revision,
          configuredProfile: "adaptive" as const, trigger: "manual" as const, context: { variant: "high" },
        }
        const starting = runtime.openRun(request)
        await expect(runtime.openRun(request)).rejects.toThrow("RUN_ACTIVE")
        planning = await starting
        expect(planning.runId).not.toBe(previousPlan.runId)
        expect(planning.goal).toBe(nextGoal)
        expect(planning.revisesPlan).toEqual(revision)
        expect(planning.contractStatus).toBe("missing")
        expect(planning.metrics.observedActions).toBe(0)
        expect(planning.evidenceRefs).toEqual([])
        expect(planning.workers).toEqual([])
        expect(planning.readyEligible).toBe(false)
        expect(opened).toHaveLength(1)
        contract = {
          ...contract, goal: nextGoal,
          criteria: contract.criteria.map(item => ({ ...item, statement: "Write revised after" })),
          claims: contract.claims.map(item => ({
            ...item, statement: "Write revised after", predicate: { type: "content_equals", value: expected },
          })),
        }
        await runtime.proposeContract("root", contract)
        runtime.beginPlanning("root")
        expect(opened).toHaveLength(2)
        expect(opened[1]!.goalSources).not.toEqual(opened[0]!.goalSources)
        expect(JSON.stringify(opened[1]!.goalSources)).toContain(nextGoal)
        const old = JSON.parse(await readFile(join(stateDirectory, previousPlan.runId + ".json"), "utf8"))
        expect(old.phase).toBe("plan_ready")
        expect(old.outcome).toBeNull()
        const revised = JSON.parse(await readFile(join(stateDirectory, planning.runId + ".json"), "utf8"))
        expect(revised.revisesPlan).toEqual(revision)
        expect(revised.goalDigest).toBe(createHash("sha256").update(nextGoal).digest("hex"))
        expect(revised.goal).toBeUndefined()
        expect(JSON.stringify(revised)).not.toContain(nextGoal)
      }
      const planningVerifierIndex = opened.length - 1
      const input = {
        planningRunId: planning.runId, planId: "reviewed-plan", planRevision: scenario === "revised" ? 2 : 1,
        goalContractHash: createHash("sha256").update(JSON.stringify(contract)).digest("hex"),
        context: { variant: scenario === "revised" ? "high" : "max" },
      }
      for (const invalid of [
        { ...input, planningRunId: "another-run" },
        { ...input, goalContractHash: "0".repeat(64) },
      ]) {
        await expect(runtime.beginPlanExecution("root", invalid)).rejects.toThrow()
        expect(runtime.status("root").runId).toBe(planning.runId)
        expect(opened).toHaveLength(planningVerifierIndex + 1)
      }
      const execution = await runtime.beginPlanExecution("root", input)
      expect(execution.runId).not.toBe(planning.runId)
      expect(execution.executionPlan).toEqual({
        planningRunId: planning.runId, planId: input.planId,
        planRevision: input.planRevision, goalContractHash: input.goalContractHash,
      })
      expect(execution.goal).toBe(planning.goal)
      expect(execution.configuredProfile).toBe("adaptive")
      expect(execution.contractStatus).toBe(rejectExecution ? "missing" : "accepted")
      if (!rejectExecution) expect(execution.phase).toBe("planning")
      expect(execution.metrics.observedActions).toBe(0)
      expect(execution.evidenceRefs).toEqual([])
      expect(execution.workers).toEqual([])
      expect(execution.readyEligible).toBe(false)
      expect(opened).toHaveLength(planningVerifierIndex + 2)
      expect(opened[planningVerifierIndex]!.runId).not.toBe(opened[planningVerifierIndex + 1]!.runId)
      expect(opened[planningVerifierIndex]!.goalSources).toEqual(opened[planningVerifierIndex + 1]!.goalSources)
      await runtime.verifyRoot("root", "manual")
      expect(verificationCalls).toBe(0)
      await expect(runtime.beginPlanExecution("root", input)).rejects.toThrow("PLAN_RUN_MISMATCH")
      expect(await readFile(join(workspace, "input.ts"), "utf8")).toBe("before")
      const archived = JSON.parse(await readFile(join(stateDirectory, planning.runId + ".json"), "utf8"))
      const persisted = JSON.parse(await readFile(join(stateDirectory, execution.runId + ".json"), "utf8"))
      expect(archived.phase).toBe("plan_ready")
      expect(archived.interrupted).toBe(false)
      expect(archived.outcome).toBeNull()
      expect(persisted.executionPlan).toEqual(execution.executionPlan)
      const graph = {
        units: [{
          id: "unit", title: "Change input", instructions: "Write " + expected, agentType: "general",
          claimIds: ["claim"], criterionIds: ["criterion"], dependsOn: [],
          readSet: ["input.ts"], writeSet: ["input.ts"], integrationRequests: [],
        }],
        integrationPaths: [],
      }
      if (scenario === "accepted" || scenario === "revised") {
        let integrated = false
        runtime.registerIntegrationExecutor(async () => { integrated = true })
        runtime.registerWorkerExecutor(async request => {
          const sessionID = "plan-worker"
          runtime.orchestration.startChild({
            parentSessionID: "root", sessionID, subagentType: "general", workUnitId: request.unit.id,
          })
          const destination = await runtime.orchestration.resolveWrite(sessionID, workspace, "input.ts")
          expect(request.context).toEqual(input.context)
          await writeFile(destination.physicalPath, expected)
          await runtime.finishWorker(sessionID, true)
          return { sessionID }
        })
        await runtime.acceptWorkGraph("root", graph, input.context)
        const finished = await runtime.verifyRoot("root", "completion")
        expect(integrated).toBe(true)
        expect(finished.workers.map(worker => worker.state)).toEqual(["completed"])
        expect(finished.outcome).toBe("ready")
        expect(finished.readyEligible).toBe(true)
        expect(finished.runId).toBe(execution.runId)
        expect(verificationCalls).toBeGreaterThanOrEqual(2)
        expect(await readFile(join(workspace, "input.ts"), "utf8")).toBe(expected)
      } else if (scenario === "dispatch-error") {
        const failed = await runtime.reportPlanExecutionFailure("root",
          Object.assign(new Error("Injected plan dispatch failure"), { code: "PLAN_DISPATCH_FAILED" }))
        expect(failed.phase).toBe("blocked")
        expect(failed.failureKind).toBe("harness_error")
        expect(failed.message).toContain("Injected plan dispatch failure")
        expect((await runtime.verifyRoot("root", "manual")).readyEligible).toBe(false)
        await expect(runtime.acceptWorkGraph("root", graph, input.context)).rejects.toThrow("ROOT_EXECUTION_FAILED")
        expect(await readFile(join(workspace, "input.ts"), "utf8")).toBe("before")
      }
      await runtime.closeWorkspace(workspace)
      await new RunRepository({ stateDirectory }).initialize()
      expect(JSON.parse(await readFile(join(stateDirectory, planning.runId + ".json"), "utf8")).phase).toBe("plan_ready")
    } finally {
      await runtime.closeWorkspace(workspace)
      runtime.resetForTest()
      for (const [key, value] of previous) {
        if (value === undefined) delete process.env[key]
        else process.env[key] = value
      }
      const rel = relative(tmpdir(), directory)
      if (rel.startsWith("..") || isAbsolute(rel)) throw new Error("Unsafe fixture cleanup")
      await rm(directory, { recursive: true, force: true })
    }
  }, 20000)
}
