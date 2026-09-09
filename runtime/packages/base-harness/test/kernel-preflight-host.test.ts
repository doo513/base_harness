import { describe, expect, test } from "bun:test"
import { KernelHost } from "../src/harness/kernel-host"

function contract(risk: "low" | "high" = "low", candidates: unknown[] = []) {
  return {
    goal: "change one file",
    criteria: [
      {
        criterionId: "criterion-1",
        statement: "the requested artifact exists",
        claimIds: ["claim-1"],
        required: true,
        risk,
      },
    ],
    claims: [
      {
        claimId: "claim-1",
        criterionIds: ["criterion-1"],
        origin: "user",
        statement: "the requested artifact exists",
        kind: "artifact",
        scope: { targets: ["one.ts"], capabilities: ["write"], exclusions: [] },
        applicability: { status: "resolved", os: "any" },
        predicate: { type: "exists" },
        verifierPolicy: {
          minimumStrength: "structural",
          allowedVerifierIds: ["file"],
          minIndependentFamilies: 1,
        },
      },
    ],
    interpretation: { version: 1, candidates },
  }
}

function harness() {
  const proposed: unknown[] = []
  const runtime = {
    openRun: async () => ({ runId: "run-1", configuredProfile: "adaptive" }),
    proposeContract: async (_sessionID: string, proposal: unknown) => {
      proposed.push(proposal)
      return { runId: "run-1", configuredProfile: "adaptive", contractStatus: "accepted" }
    },
    acceptWorkGraph: async () => ({}),
    status: () => ({ runId: "run-1", configuredProfile: "adaptive" }),
  }
  return { host: new KernelHost(runtime), proposed }
}

describe("KernelHost selective contract preflight", () => {
  test("does not call a reviewer for a clear atomic contract", async () => {
    const { host, proposed } = harness()
    await host.openRun({ sessionID: "s1", workspace: ".", goal: "one file" })
    const status = await host.proposeContract("s1", contract())
    expect(status.preflight.decision).toBe("accept")
    expect(status.preflight.reviewerCallCount).toBe(0)
    expect(proposed).toHaveLength(1)
    expect((proposed[0] as Record<string, unknown>).interpretation).toBeUndefined()
  })

  test("asks for input before forwarding consequential ambiguity", async () => {
    const { host, proposed } = harness()
    await host.openRun({ sessionID: "s1", workspace: ".", goal: "choose format" })
    const status = await host.proposeContract(
      "s1",
      contract("low", [
        {
          id: "u1",
          kind: "missing_decision",
          impact: "user_preference",
          affectedClaimIds: ["claim-1"],
          affectedCriterionIds: ["criterion-1"],
          sourceRefs: [{ source: "user_prompt" }],
          statement: "The output format is not selected.",
        },
      ]),
    )
    expect(status.planningState).toBe("awaiting_input")
    expect(status.preflight.questionCount).toBe(1)
    expect(proposed).toHaveLength(0)
  })

  test("calls the reviewer once for a high-risk contract", async () => {
    const { host, proposed } = harness()
    let calls = 0
    host.registerMetaReviewer(async () => {
      calls += 1
      return { phase: "goal_contract", outcome: "pass", issues: [] }
    })
    await host.openRun({ sessionID: "s1", workspace: ".", goal: "high risk" })
    const status = await host.proposeContract("s1", contract("high"))
    expect(calls).toBe(1)
    expect(status.preflight.reviewerCallCount).toBe(1)
    expect(proposed).toHaveLength(1)
  })

  test("only a typed trigger reopens the affected contract", async () => {
    const { host } = harness()
    await host.openRun({ sessionID: "s1", workspace: ".", goal: "one file" })
    await host.proposeContract("s1", contract())
    const status = host.revalidateContract("s1", "scope_expansion_requested", ["claim-1"])
    expect(status.planningState).toBe("contract_building")
    expect(status.preflight.revalidationTrigger).toBe("scope_expansion_requested")
    expect(status.preflight.affectedClaimIds).toEqual(["claim-1"])
  })
})
