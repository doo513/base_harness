import { expect, spyOn, test } from "bun:test"
import { KernelHost } from "@base-harness/kernel-host"
import { contractFixture } from "../../../kernel-host/test/contract-fixture"
import { ExecutionBackends } from "../../src/harness/execution/backend-router"
import { executeExternalGoal } from "../../src/harness/external-execution"

for (const outcome of ["needs_input", "revision_required"] as const) {
  test(`external contract ${outcome} pauses without graph dispatch or Runtime admission`, async () => {
    const current = { sessionID: "root", runId: "run", phase: "planning", contractStatus: "accepted", evidenceCount: 0, readyEligible: false }
    let admitted = 0, graphs = 0
    const host = new KernelHost({
      openRun: async () => current, status: () => current,
      proposeContract: async () => { admitted++; return current },
      acceptWorkGraph: async () => { graphs++; return current },
    })
    await host.openRun({ sessionID: "root", workspace: "/fixture", goal: "Create a report" })
    host.registerMetaReviewer(async () => ({ phase: "goal_contract", outcome: "revise", issues: [{
      id: "fix", kind: "omission", severity: "blocking", targetIds: ["k"], sourceRefs: [{ source: "request" }],
      statement: "Correct the required result from the supplied request",
    }] }))
    const contract = contractFixture({
      criteria: [{ criterionId: "k", claimIds: ["c"], risk: outcome === "needs_input" ? "low" : "high" }],
      claims: [{ claimId: "c", criterionIds: ["k"], applicability: {} }],
      interpretation: { version: 1, candidates: outcome === "needs_input" ? [{
        id: "format", kind: "missing_decision", impact: "user_preference", affectedClaimIds: ["c"],
        affectedCriterionIds: ["k"], sourceRefs: [{ source: "request" }], statement: "Select the report format",
      }] : [] },
    })
    const submit = host.proposeContract.bind(host), dispatch = host.acceptWorkGraph.bind(host)
    const stageProposal = host.stageExecutionProposal.bind(host), statusView = host.status.bind(host)
    const propose = spyOn(KernelHost.prototype, "proposeContract").mockImplementation(submit)
    const graph = spyOn(KernelHost.prototype, "acceptWorkGraph").mockImplementation(dispatch)
    const stage = spyOn(KernelHost.prototype, "stageExecutionProposal").mockImplementation(stageProposal)
    const status = spyOn(KernelHost.prototype, "status").mockImplementation(statusView)
    const calls: string[] = []
    const execute = spyOn(ExecutionBackends, "execute").mockImplementation(async (request) => {
      calls.push(request.phase ?? "")
      return { output: JSON.stringify({ contract, workGraph: { integrationPaths: [], units: [{
        id: "u", title: "Report", instructions: "Create report.txt", claimIds: ["c"], criterionIds: ["k"],
        dependsOn: [], readSet: [], writeSet: ["report.txt"], integrationRequests: [],
      }] } }), changedFiles: [], backendId: request.selection.backendId, modelId: request.selection.modelId,
      capabilityRevision: "fixture", nativeOptions: {} }
    })
    try {
      const result = await executeExternalGoal({ sessionID: "root", workspace: "/fixture", goal: "Create a report",
        context: {}, authoringSkill: "Fixture authoring instructions", execution: { backendId: "codex-app-server", modelId: "fixture" } })
      expect(result.status).toMatchObject({ contractProcessing: { outcome }, evidenceCount: 0, readyEligible: false })
      expect(host.hasAcceptedContract("root")).toBe(false)
      expect(admitted).toBe(0)
      expect(graphs).toBe(0)
      expect(calls).toEqual(["plan"])
    } finally {
      execute.mockRestore()
      status.mockRestore()
      stage.mockRestore()
      graph.mockRestore()
      propose.mockRestore()
    }
  })
}

test("external General planning accepts a contract-only response without WorkGraph or writeSet", async () => {
  const current = { sessionID: "general-root", runId: "general-run", phase: "planning", contractStatus: "missing", evidenceCount: 0, readyEligible: false }
  let admitted = 0
  const host = new KernelHost({
    openRun: async () => current,
    status: () => current,
    proposeContract: async () => { admitted += 1; return current },
    acceptWorkGraph: async () => { throw new Error("General must not dispatch a WorkGraph") },
  })
  await host.control("general-root", { type: "domain.set", domain: "general" })
  await host.openRun({ sessionID: "general-root", workspace: "/fixture", goal: "Inspect a report" })
  const proposal = contractFixture({
    goal: "Inspect a report",
    criteria: [{ criterionId: "k", claimIds: ["c"], risk: "low" }],
    claims: [{
      claimId: "c",
      criterionIds: ["k"],
      scope: { targets: ["report"], capabilities: ["read"], exclusions: [] },
      applicability: {},
      predicate: { type: "output_contains", value: "result" },
    }],
    interpretation: { version: 1, candidates: [{
      id: "source", kind: "missing_decision", impact: "user_preference", affectedClaimIds: ["c"],
      affectedCriterionIds: ["k"], sourceRefs: [{ source: "request" }], statement: "Select the source",
    }] },
  })
  const submitProposal = host.proposeContract.bind(host)
  const stageProposal = host.stageExecutionProposal.bind(host)
  const statusView = host.status.bind(host)
  const submit = spyOn(KernelHost.prototype, "proposeContract").mockImplementation(submitProposal)
  const stage = spyOn(KernelHost.prototype, "stageExecutionProposal").mockImplementation(stageProposal)
  const status = spyOn(KernelHost.prototype, "status").mockImplementation(statusView)
  const calls: Parameters<typeof ExecutionBackends.execute>[0][] = []
  const execute = spyOn(ExecutionBackends, "execute").mockImplementation(async (request) => {
    calls.push(request)
    return {
      output: JSON.stringify({ contract: proposal }),
      changedFiles: [],
      backendId: request.selection.backendId,
      modelId: request.selection.modelId,
      capabilityRevision: "fixture",
      nativeOptions: {},
    }
  })
  try {
    const result = await executeExternalGoal({
      sessionID: "general-root",
      workspace: "/fixture",
      goal: "Inspect a report",
      context: {},
      authoringSkill: "Fixture authoring instructions",
      execution: { backendId: "codex-app-server", modelId: "fixture" },
    })
    expect(result.status).toMatchObject({ contractProcessing: { outcome: "needs_input" } })
    expect(admitted).toBe(0)
    expect(calls).toHaveLength(1)
    const body = JSON.parse(calls[0]!.prompt)
    expect(body.domain).toBe("general")
    expect(body.response).not.toHaveProperty("workGraph")
    expect(JSON.stringify(body.response)).not.toContain("writeSet")
    expect(calls[0]!.runId).toBe("general-run")
  } finally {
    execute.mockRestore()
    status.mockRestore()
    stage.mockRestore()
    submit.mockRestore()
  }
})
