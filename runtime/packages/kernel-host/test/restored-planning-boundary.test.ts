import { expect, test } from "bun:test"
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import { KernelHost } from "../src"
import type { MetaReviewRequest } from "../src"
import type { PlanSpec } from "@base-harness/kernel"

async function fixture(body: (value: {
  host: KernelHost; workspace: string; graph: any;
  control: {
    continuation: boolean; opens: number; executionOpens: number; runId: string; accepted: any[];
    reviews: string[]; executionGate?: Promise<void>; executionStarted?: () => void; rejectExecution: boolean;
    phase?: string; dispatchError?: Error; dispatchFailures?: unknown[];
  };
}) => Promise<void>, review?: (request: MetaReviewRequest, workspace: string) => Promise<unknown>) {
  const directory = await mkdtemp(join(tmpdir(), "harness-plan-boundary-"))
  const workspace = join(directory, "workspace"), state = join(directory, "state")
  await mkdir(workspace)
  await mkdir(state)
  await writeFile(join(workspace, "input.ts"), "export const value = 1\n")
  const keys = ["LOCALAPPDATA", "XDG_STATE_HOME"]
  const previous = new Map(keys.map(key => [key, process.env[key]]))
  for (const key of keys) process.env[key] = state
  const control: {
    continuation: boolean; opens: number; executionOpens: number; runId: string; accepted: any[];
    reviews: string[]; executionGate?: Promise<void>; executionStarted?: () => void; rejectExecution: boolean;
    phase?: string; dispatchError?: Error; dispatchFailures?: unknown[];
  } = { continuation: false, opens: 0, executionOpens: 0, runId: "run", accepted: [], reviews: [], rejectExecution: false }
  const runtime = {
    openRun: async (input: any) => {
      control.opens++
      return { sessionID: input.sessionID, runId: "run", phase: "planning", goal: "Original goal" }
    },
    proposeContract: async () => ({ sessionID: "root", runId: "run", phase: "planning", contractStatus: "accepted" }),
    acceptWorkGraph: async (_id: string, graph: any) => {
      if (control.dispatchError) throw control.dispatchError
      control.accepted.push(graph)
      return { sessionID: "root", runId: "run", phase: "scheduling" }
    },
    beginPlanExecution: async (_id: string, input: any) => {
      expect(input.planningRunId).toBe(control.runId)
      control.executionOpens++
      control.executionStarted?.()
      await control.executionGate
      control.runId = "execution-" + control.executionOpens
      return {
        sessionID: "root", runId: control.runId, phase: control.rejectExecution ? "blocked" : "planning",
        contractStatus: control.rejectExecution ? "missing" : "accepted", goal: "Original goal",
      }
    },
    reportPlanExecutionFailure: async (_id: string, error: unknown) => {
      control.dispatchFailures = [...(control.dispatchFailures ?? []), error]
      control.phase = "blocked"
    },
    status: () => ({
      sessionID: "root", runId: control.runId, phase: control.phase ?? "planning", goal: "Original goal",
      failureKind: control.dispatchFailures?.length ? "harness_error" : undefined,
    }),
    isInternalContinuation: () => control.continuation,
  }
  const host = new KernelHost(runtime)
  host.registerMetaReviewer(request => {
    control.reviews.push(request.phase)
    return review ? review(request, workspace)
      : Promise.resolve({ phase: request.phase, outcome: "pass", issues: [] })
  })
  const graph = { units: [{
    id: "unit", title: "Change input", instructions: "original instructions", agentType: "general",
    claimIds: ["claim"], criterionIds: ["criterion"], dependsOn: [],
    readSet: ["input.ts"], writeSet: ["input.ts"], integrationRequests: [],
  }], integrationPaths: [] }
  try {
    await host.control("root", { type: "planning.plan_once" })
    await host.openRun({ sessionID: "root", workspace, goal: "Original goal" })
    await host.proposeContract("root", {
      goal: "Original goal", interpretation: { version: 1, candidates: [] },
      criteria: [{ criterionId: "criterion", statement: "Change input", claimIds: ["claim"], required: true, risk: "low" }],
      claims: [{
        claimId: "claim", statement: "Change input", criterionIds: ["criterion"], required: true,
        applicability: { status: "applicable" }, verifierPolicy: { minIndependentFamilies: 1 },
        scope: { targets: ["input.ts"] },
      }],
    })
    await body({ host, workspace, graph, control })
  } finally {
    for (const [key, value] of previous) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    const rel = relative(tmpdir(), directory)
    if (rel.startsWith("..") || isAbsolute(rel)) throw new Error("Unsafe fixture cleanup")
    await rm(directory, { recursive: true, force: true })
  }
}

test("trusted root continuation preserves the reviewed plan and original contract", async () => {
  await fixture(async ({ host, workspace, graph, control }) => {
    const planned = await host.acceptWorkGraph("root", graph)
    await host.control("root", { type: "planning.execute", planId: planned.activePlanId })
    control.continuation = true
    const continued = await host.openRun({ sessionID: "root", workspace, goal: "Internal repair instructions", context: { changed: true } })
    expect(continued.planningState).toBe("executing")
    expect(continued.activePlanId).toBe(planned.activePlanId)
    expect(continued.goalContract.hash).toBe(planned.goalContract.hash)
    expect(continued.goal).toBe("Original goal")
    expect(control.opens).toBe(1)
    expect(control.accepted).toHaveLength(1)
    expect(control.executionOpens).toBe(1)
  })
})

test("a continuation for another workspace fails without resetting the accepted plan", async () => {
  await fixture(async ({ host, workspace, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    await host.control("root", { type: "planning.execute" })
    control.continuation = true
    const error = await host.openRun({ sessionID: "root", workspace: join(workspace, "other"), goal: "Internal" }).then(() => null, error => error)
    expect(error).toMatchObject({ code: "ROOT_CONTINUATION_MISMATCH" })
    expect(host.status("root").planningState).toBe("executing")
    expect(control.opens).toBe(1)
  })
})

test("untrusted input flags cannot grant continuation authority", async () => {
  await fixture(async ({ host, workspace, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    await host.control("root", { type: "planning.execute" })
    const ordinary = await host.openRun({ sessionID: "root", workspace, goal: "New request", internalContinuation: true, synthetic: true })
    expect(ordinary.planningState).toBe("contract_building")
    expect(control.opens).toBe(2)
  })
})

test("caller mutation cannot replace the stored reviewed execution graph", async () => {
  await fixture(async ({ host, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    graph.units[0].instructions = "unreviewed replacement"
    graph.units[0].writeSet = ["outside.ts"]
    await host.control("root", { type: "planning.execute" })
    expect(control.accepted[0].units[0].instructions).toBe("original instructions")
    expect(control.accepted[0].units[0].writeSet).toEqual(["input.ts"])
  })
})

test("a revised and re-reviewed graph, not the original proposal, is dispatched", async () => {
  await fixture(async ({ host, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    await host.control("root", { type: "planning.execute" })
    expect(control.accepted[0].units[0].instructions).toBe("reviewed instructions")
  }, async request => {
    if (request.attempt === 2) return { phase: request.phase, outcome: "pass", issues: [] }
    const plan = structuredClone(request.artifact) as PlanSpec
    ;(plan.workGraph as any).units[0].instructions = "reviewed instructions"
    return { phase: request.phase, outcome: "revise", issues: [{
      id: "refine", kind: "coverage", severity: "blocking", targetIds: ["unit"], sourceRefs: [], statement: "Refine fixture instructions",
    }], revisedArtifact: plan }
  })
})

for (const mutation of ["identity", "steps", "basis"] as const) {
  test("invalid reviewed execution binding is rejected before dispatch: " + mutation, async () => {
    await fixture(async ({ host, graph, control }) => {
      const error = await host.acceptWorkGraph("root", graph).then(() => null, error => error)
      expect(error).toMatchObject({ code: mutation === "identity" ? "PLAN_IDENTITY_MISMATCH" : mutation === "steps" ? "PLAN_GRAPH_MISMATCH" : "PLAN_BASIS_MISMATCH" })
      expect(control.accepted).toHaveLength(0)
      expect(() => host.assertToolAllowed("root", "write")).toThrow()
    }, async (request, workspace) => {
      if (mutation === "basis") {
        await writeFile(join(workspace, "input.ts"), "changed while the review was running\n")
        return { phase: request.phase, outcome: "pass", issues: [] }
      }
      if (request.attempt === 2) return { phase: request.phase, outcome: "pass", issues: [] }
      const plan = structuredClone(request.artifact) as PlanSpec
      if (mutation === "identity") plan.goalContractHash = "f".repeat(64)
      else plan.steps[0]!.writeSet = ["other.ts"]
      return { phase: request.phase, outcome: "revise", issues: [{
        id: "change", kind: "scope", severity: "blocking", targetIds: ["unit"], sourceRefs: [], statement: "Fixture change",
      }], revisedArtifact: plan }
    })
  })
}


test("execute opens a fresh run without reviewing the same plan again", async () => {
  await fixture(async ({ host, graph, control }) => {
    const events: any[] = []
    const off = host.subscribe(status => events.push(status))
    try {
      const planned = await host.acceptWorkGraph("root", graph)
      const execution = await host.control("root", { type: "planning.execute" })
      expect(execution.runId).not.toBe(planned.runId)
      expect(execution.activePlanId).toBe(planned.activePlanId)
      expect(execution.activePlanRevision).toBe(planned.activePlanRevision)
      expect(execution.goalContract.hash).toBe(planned.goalContract.hash)
      expect(control.reviews).toEqual(["plan"])
      expect(control.executionOpens).toBe(1)
      expect(events.some(event => event.planningState === "plan_ready")).toBe(true)
      expect(events.some(event => event.planningState === "executing" && event.runId === execution.runId)).toBe(true)
    } finally { off() }
  })
})

test("concurrent execute controls cannot dispatch the same reviewed plan twice", async () => {
  await fixture(async ({ host, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    let release!: () => void
    control.executionGate = new Promise<void>(resolve => { release = resolve })
    const executing = host.control("root", { type: "planning.execute" })
    try {
      const error = await host.control("root", { type: "planning.execute" }).then(() => null, error => error)
      expect(error).toMatchObject({ code: "RUN_ACTIVE" })
    } finally { release() }
    await executing
    expect(control.executionOpens).toBe(1)
    expect(control.accepted).toHaveLength(1)
  })
})

test("a fresh verifier rejecting the contract prevents worker dispatch", async () => {
  await fixture(async ({ host, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    control.rejectExecution = true
    const result = await host.control("root", { type: "planning.execute" })
    expect(result.planningState).toBe("awaiting_input")
    expect(control.accepted).toHaveLength(0)
    expect(() => host.assertToolAllowed("root", "write")).toThrow()
  })
})

test("changed planning basis is rejected before the execution run opens", async () => {
  await fixture(async ({ host, workspace, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    await writeFile(join(workspace, "input.ts"), "unrelated edit after planning\n")
    const error = await host.control("root", { type: "planning.execute" }).then(() => null, error => error)
    expect(error).toMatchObject({ code: "PLAN_STALE" })
    expect(control.executionOpens).toBe(0)
    expect(control.accepted).toHaveLength(0)
    expect(host.status("root").planningState).toBe("plan_building")
  })
})


test("Host dispatch failure is blocked instead of asking the user to resolve an internal error", async () => {
  await fixture(async ({ host, graph, control }) => {
    await host.acceptWorkGraph("root", graph)
    control.dispatchError = new Error("Injected WorkGraph dispatch failure")
    await expect(host.control("root", { type: "planning.execute" })).rejects.toThrow("Injected WorkGraph dispatch failure")
    expect(control.dispatchFailures).toEqual([control.dispatchError])
    expect(control.accepted).toHaveLength(0)
    expect(host.status("root").phase).toBe("blocked")
    expect(host.status("root").failureKind).toBe("harness_error")
    expect(host.status("root").planningState).toBe("idle")
    expect(control.reviews).toEqual(["plan"])
  })
})


test("an active execute rejects duplicates without waiting and does not lock another session", async () => {
  await fixture(async ({ host, graph, control }) => {
    const planned = await host.acceptWorkGraph("root", graph)
    let release!: () => void
    let entered!: () => void
    const started = new Promise<void>(resolve => { entered = resolve })
    control.executionGate = new Promise<void>(resolve => { release = resolve })
    control.executionStarted = entered
    const executing = host.control("root", { type: "planning.execute", planId: planned.activePlanId })
    try {
      await started
      expect(control.executionOpens).toBe(1)
      await expect(host.control("root", { type: "planning.execute", planId: planned.activePlanId }))
        .rejects.toMatchObject({ code: "RUN_ACTIVE" })
      await expect(host.control("other", { type: "planning.execute" }))
        .rejects.toMatchObject({ code: "PLAN_NOT_READY" })
      expect(control.accepted).toHaveLength(0)
    } finally {
      release()
      await executing
    }
    expect(control.accepted).toHaveLength(1)
  })
}, 10000)

test("failed execute validation releases admission without consuming the reviewed plan", async () => {
  await fixture(async ({ host, graph, control }) => {
    const planned = await host.acceptWorkGraph("root", graph)
    await expect(host.control("root", { type: "planning.execute", planId: "different-plan" }))
      .rejects.toMatchObject({ code: "PLAN_ID_MISMATCH" })
    expect(control.executionOpens).toBe(0)
    const execution = await host.control("root", { type: "planning.execute", planId: planned.activePlanId })
    expect(execution.activePlanId).toBe(planned.activePlanId)
    expect(control.executionOpens).toBe(1)
    expect(control.accepted).toHaveLength(1)
  })
}, 10000)
