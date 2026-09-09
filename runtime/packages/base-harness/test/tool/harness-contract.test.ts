import { expect, spyOn, test } from "bun:test"
import { KernelHost } from "@base-harness/kernel-host"
import {
  assertHarnessContractSubmitted,
  registerHarnessContractProposal,
  type HarnessContractProposal,
} from "../../src/tool/harness-contract-state"

const proposal = (): HarnessContractProposal => ({
  goal: "verify contract gating",
  interpretation: { version: 1, candidates: [] },
  criteria: [
    {
      criterionId: "criterion-1",
      statement: "The requested behavior is verified",
      claimIds: ["claim-1"],
      required: true,
      risk: "low",
    },
  ],
  claims: [
    {
      claimId: "claim-1",
      criterionIds: ["criterion-1"],
      origin: "user",
      statement: "The requested behavior is verified",
      kind: "execution",
      scope: {
        targets: ["result.txt"],
        capabilities: ["requested_behavior"],
        exclusions: [],
      },
      applicability: { os: process.platform },
      predicate: { type: "command_exit", expectedExitCode: 0 },
      verifierPolicy: {
        minimumStrength: "execution",
        allowedVerifierIds: ["auto"],
        minIndependentFamilies: 1,
      },
    },
  ],
  constraints: [],
})


async function withGate(
  options: { planOnly?: boolean; reject?: boolean },
  run: (fixture: { sessionID: string; host: KernelHost; proposals: () => number }) => Promise<void>,
) {
  const sessionID = "gate-" + crypto.randomUUID()
  let proposals = 0
  let current = {
    sessionID, runId: "run-" + sessionID, phase: "planning",
    contractStatus: "pending", effectiveProfile: "adaptive",
  }
  const runtime: ConstructorParameters<typeof KernelHost>[0] = {
    openRun: async () => current,
    proposeContract: async () => {
      proposals += 1
      current = { ...current, contractStatus: options.reject ? "rejected" : "accepted" }
      return current
    },
    acceptWorkGraph: async () => current,
    status: () => current,
  }
  const host = new KernelHost(runtime)
  // Bind the real Kernel methods before redirecting the shared adapter. Permission
  // decisions are not mocked, and no module replacement leaks into later tests.
  const submit = host.proposeContract.bind(host)
  const admit = host.assertToolAllowed.bind(host)
  const submitSpy = spyOn(KernelHost.prototype, "proposeContract").mockImplementation(submit)
  const admitSpy = spyOn(KernelHost.prototype, "assertToolAllowed").mockImplementation(admit)
  try {
    if (options.planOnly) await host.control(sessionID, { type: "planning.plan_once" })
    await host.openRun({ sessionID, workspace: process.cwd(), goal: "verify contract gating" })
    await run({ sessionID, host, proposals: () => proposals })
  } finally {
    admitSpy.mockRestore()
    submitSpy.mockRestore()
  }
}

function expectMutationDenied(sessionID: string) {
  expect(() => assertHarnessContractSubmitted(sessionID, "write")).toThrow()
  expect(() => assertHarnessContractSubmitted(sessionID, "mcp_database_write", "mutate")).toThrow()
  expect(() => assertHarnessContractSubmitted(sessionID, "read")).not.toThrow()
}

test("state-changing and dynamic MCP tools wait for accepted contract admission", async () => {
  await withGate({}, async ({ sessionID, proposals }) => {
    expectMutationDenied(sessionID)
    const pending = registerHarnessContractProposal(sessionID, proposal())
    expectMutationDenied(sessionID)
    const status = await pending
    expect(proposals()).toBe(1)
    expect(status.contractStatus).toBe("accepted")
    expect(status.planningState).toBe("executing")
    expect(status.preflight.mutatingActionAllowed).toBe(true)
    expect(() => assertHarnessContractSubmitted(sessionID, "write")).not.toThrow()
    expect(() => assertHarnessContractSubmitted(sessionID, "mcp_database_write", "mutate")).not.toThrow()
  })
})

test("invalid bidirectional binding never reaches runtime acceptance", async () => {
  await withGate({}, async ({ sessionID, proposals }) => {
    const invalid = proposal()
    invalid.criteria[0]!.claimIds = ["missing-claim"]
    await expect(registerHarnessContractProposal(sessionID, invalid)).rejects.toThrow(
      "Criterion-Claim binding must be bidirectional",
    )
    expect(proposals()).toBe(0)
    expectMutationDenied(sessionID)
  })
})

test("missing interpretation is rejected without opening the gate", async () => {
  await withGate({}, async ({ sessionID, proposals }) => {
    const invalid = { ...proposal(), interpretation: undefined } as unknown as HarnessContractProposal
    await expect(registerHarnessContractProposal(sessionID, invalid)).rejects.toThrow("INTERPRETATION_SCHEMA")
    expect(proposals()).toBe(0)
    expectMutationDenied(sessionID)
  })
})

test("runtime rejection keeps a valid preflight proposal non-mutating", async () => {
  await withGate({ reject: true }, async ({ sessionID, proposals }) => {
    const status = await registerHarnessContractProposal(sessionID, proposal())
    expect(proposals()).toBe(1)
    expect(status.contractStatus).toBe("rejected")
    expect(status.preflight.mutatingActionAllowed).toBe(false)
    expectMutationDenied(sessionID)
  })
})

test("plan-only keeps mutation denied even after runtime contract acceptance", async () => {
  await withGate({ planOnly: true }, async ({ sessionID }) => {
    const status = await registerHarnessContractProposal(sessionID, proposal())
    expect(status.contractStatus).toBe("accepted")
    expect(status.planningState).toBe("planning_decision")
    expect(status.planOnly).toBe(true)
    expectMutationDenied(sessionID)
  })
})

test("a previously submitted contract cannot bypass typed revalidation", async () => {
  await withGate({}, async ({ sessionID, host }) => {
    await registerHarnessContractProposal(sessionID, proposal())
    expect(() => assertHarnessContractSubmitted(sessionID, "write")).not.toThrow()
    host.revalidateContract(sessionID, "scope_expansion_requested", ["claim-1"], ["criterion-1"])
    expectMutationDenied(sessionID)
    expect(host.canVerifyRoot(sessionID)).toBe(false)
  })
})

test("consequential ambiguity pauses before runtime contract acceptance", async () => {
  await withGate({}, async ({ sessionID, proposals }) => {
    const input = proposal()
    input.interpretation.candidates.push({
      id: "required-result",
      kind: "missing_decision",
      impact: "required_criterion",
      affectedClaimIds: ["claim-1"],
      affectedCriterionIds: ["criterion-1"],
      sourceRefs: [{ source: "user", quote: input.goal }],
      statement: "The required result needs a user decision.",
    })
    const status = await registerHarnessContractProposal(sessionID, input)
    expect(proposals()).toBe(0)
    expect(status.planningState).toBe("awaiting_input")
    expect(status.preflight.decision).toBe("needs_input")
    expectMutationDenied(sessionID)
  })
})

test("only read-only exploration may delegate before contract acceptance", async () => {
  await withGate({}, async ({ sessionID, proposals }) => {
    expect(() => assertHarnessContractSubmitted(sessionID, "task", undefined, "explore")).not.toThrow()
    expect(() => assertHarnessContractSubmitted(sessionID, "task", undefined, "general")).toThrow()
    expect(() => assertHarnessContractSubmitted(sessionID, "task")).toThrow()
    expect(proposals()).toBe(0)
    expectMutationDenied(sessionID)
  })
})
