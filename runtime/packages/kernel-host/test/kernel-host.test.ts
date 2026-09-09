import { describe, expect, test } from "bun:test"
import { mkdtemp, writeFile } from "node:fs/promises"
import { rmSync } from "node:fs"
import os from "node:os"
import path from "node:path"
import { KernelHost } from "../src"

const cleanup: string[] = []
process.once("exit", () => {
  for (const entry of cleanup.splice(0)) rmSync(entry, { recursive: true, force: true })
})

describe("KernelHost", () => {
  test("keeps plan-only work immutable until typed execute", async () => {
    const workspace = await mkdtemp(path.join(os.tmpdir(), "base-harness-kernel-workspace-"))
    const state = await mkdtemp(path.join(os.tmpdir(), "base-harness-kernel-state-"))
    cleanup.push(workspace, state)
    await writeFile(path.join(workspace, "input.ts"), "export const value = 1\n")
    const previous = process.env.LOCALAPPDATA
    process.env.LOCALAPPDATA = state
    let accepted = 0
    let currentRunId = "run-s1"
    const runtime = {
      openRun: async (input: any) => ({ sessionID: input.sessionID, runId: "run-s1", phase: "planning" }),
      proposeContract: async () => ({ sessionID: "s1", runId: "run-s1", phase: "planning", contractStatus: "accepted" }),
      acceptWorkGraph: async () => {
        accepted += 1
        return { sessionID: "s1", runId: "run-s1", phase: "scheduling" }
      },
      beginPlanExecution: async () => {
        currentRunId = "execution-s1"
        return { sessionID: "s1", runId: currentRunId, phase: "planning", contractStatus: "accepted" }
      },
      status: () => ({ sessionID: "s1", runId: currentRunId, phase: "planning" }),
    }
    const host = new KernelHost(runtime)
    host.registerMetaReviewer(async (request) => ({
      phase: request.phase,
      outcome: "pass",
      issues: [],
    }))
    try {
      await host.control("s1", { type: "planning.plan_once" })
      await host.openRun({ sessionID: "s1", workspace, goal: "change input" })
      await host.proposeContract("s1", {
        interpretation: { version: 1, candidates: [] },
        criteria: [{
          criterionId: "criterion-1",
          claimIds: ["claim-1"],
          required: true,
          risk: "low",
        }],
        claims: [{
          claimId: "claim-1",
          criterionIds: ["criterion-1"],
          required: true,
          applicability: { status: "applicable" },
          verifierPolicy: { minimumEvidenceFamilies: 1 },
        }],
      })
      const status = await host.acceptWorkGraph("s1", {
        units: [{
          id: "unit-1",
          title: "Change input",
          claimIds: ["claim-1"],
          criterionIds: ["criterion-1"],
          dependsOn: [],
          readSet: ["input.ts"],
          writeSet: ["input.ts"],
        }],
      })
      expect(status.planningState).toBe("plan_ready")
      expect(accepted).toBe(0)
      expect(() => host.assertToolAllowed("s1", "edit")).toThrow("PLAN_ONLY_MUTATION_DENIED")
      const execution = await host.control("s1", { type: "planning.execute", planId: status.activePlanId })
      expect(execution.runId).not.toBe(status.runId)
      expect(execution.activePlanId).toBe(status.activePlanId)
      expect(accepted).toBe(1)
    } finally {
      if (previous === undefined) delete process.env.LOCALAPPDATA
      else process.env.LOCALAPPDATA = previous
    }
  })

  test("denies unclassified and mutating tools in general", async () => {
    const runtime = {
      openRun: async () => ({ sessionID: "s2", runId: "run-s2", phase: "planning" }),
      proposeContract: async () => ({}),
      acceptWorkGraph: async () => ({}),
      status: () => ({ sessionID: "s2", runId: "run-s2", phase: "inactive" }),
    }
    const host = new KernelHost(runtime)
    await host.control("s2", { type: "domain.set", domain: "general" })
    expect(() => host.assertToolAllowed("s2", "read")).not.toThrow()
    expect(() => host.assertToolAllowed("s2", "edit")).toThrow("DOMAIN_PERMISSION_DENIED")
    expect(() => host.assertToolAllowed("s2", "untyped_mcp_action")).toThrow("DOMAIN_PERMISSION_UNKNOWN")
  })
})
