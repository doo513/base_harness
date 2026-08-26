import { expect, test } from "bun:test"
import {
  assertHarnessContractSubmitted,
  registerHarnessContractProposal,
  type HarnessContractProposal,
} from "../../src/tool/harness-contract-state"

const proposal = (): HarnessContractProposal => ({
  goal: "verify contract gating",
  criteria: [
    {
      criterionId: "criterion-1",
      statement: "The requested behavior is verified",
      claimIds: ["claim-1"],
      required: true,
      risk: "medium",
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
        targets: ["workspace"],
        capabilities: ["requested_behavior"],
        exclusions: [],
      },
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

test("state-changing and dynamic MCP tools require a submitted contract", () => {
  const sessionID = "gate-" + crypto.randomUUID()
  expect(() => assertHarnessContractSubmitted(sessionID, "write")).toThrow()
  expect(() => assertHarnessContractSubmitted(sessionID, "mcp_database_write")).toThrow()
  expect(() => assertHarnessContractSubmitted(sessionID, "read")).not.toThrow()

  registerHarnessContractProposal(sessionID, proposal())

  expect(() => assertHarnessContractSubmitted(sessionID, "write")).not.toThrow()
  expect(() => assertHarnessContractSubmitted(sessionID, "mcp_database_write")).not.toThrow()
})

test("invalid bidirectional binding never opens the session gate", () => {
  const sessionID = "invalid-" + crypto.randomUUID()
  const invalid = proposal()
  invalid.criteria[0]!.claimIds = ["missing-claim"]

  expect(() => registerHarnessContractProposal(sessionID, invalid)).toThrow(
    "Criterion-Claim binding must be bidirectional",
  )
  expect(() => assertHarnessContractSubmitted(sessionID, "write")).toThrow()
})
