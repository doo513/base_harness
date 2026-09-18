import { expect, test } from "bun:test"
import { defaultContractReviewPolicy, reviewContractFacts } from "@base-harness/kernel"
import type { ContractReviewFacts, ContractReviewPolicy } from "@base-harness/domain-contracts"
import { KernelHost } from "../src"
import { contractFixture } from "./contract-fixture"

const facts: ContractReviewFacts = {
  interpretation: { version: 1, candidates: [] },
  signals: { risk: "low", configuredProfile: "adaptive", requiredClaimCount: 1, requiredCriterionCount: 1, hasExternalClaim: false, applicabilityResolved: true },
}
const proposal = () => contractFixture({
  criteria: [{ criterionId: "k", claimIds: ["c"] }],
  claims: [{ claimId: "c", criterionIds: ["k"], applicability: {} }],
})

test("the default policy preserves the decision matrix and consequential uncertainty precedence", () => {
  expect(reviewContractFacts(facts).decision).toBe("proceed")
  for (const [patch, reason] of [
    [{ risk: "high" }, "high_risk"], [{ risk: "critical" }, "high_risk"],
    [{ configuredProfile: "strict" }, "strict_profile"], [{ hasExternalClaim: true }, "external_side_effect"],
    [{ applicabilityResolved: false }, "applicability_gap"],
    [{ requiredClaimCount: 2 }, "complex_contract"], [{ requiredCriterionCount: 2 }, "complex_contract"],
  ] as const) {
    const result = reviewContractFacts({ ...facts, signals: { ...facts.signals, ...patch } })
    expect(result.decision).toBe("meta_review_required")
    expect(result.reasons).toEqual([reason])
  }
  const uncertainty: ContractReviewFacts = structuredClone(facts)
  uncertainty.signals.risk = "critical"
  uncertainty.interpretation.candidates.push({ id: "u", kind: "missing_decision", impact: "user_preference",
    affectedClaimIds: ["c"], affectedCriterionIds: ["k"], sourceRefs: [{ source: "request" }], statement: "Select the format" })
  expect(reviewContractFacts(uncertainty)).toMatchObject({ decision: "needs_input", reasons: ["missing_required_value"] })
})

function fixture(policy: ContractReviewPolicy) {
  let proposed = 0, reviewed = 0
  const host = new KernelHost({
    openRun: async () => ({ runId: "run", phase: "planning" }),
    status: () => ({ runId: "run", phase: "planning" }),
    proposeContract: async () => { proposed++; return { runId: "run", contractStatus: "accepted" } },
    acceptWorkGraph: async () => ({}),
  }, { contractReviewPolicy: policy })
  host.registerMetaReviewer(async () => { reviewed++; return { phase: "goal_contract", outcome: "pass", issues: [] } })
  return { host, proposed: () => proposed, reviewed: () => reviewed }
}

test("Host injects a replacement policy while retaining Runtime acceptance", async () => {
  const policy: ContractReviewPolicy = { evaluate: (input) => ({ ...defaultContractReviewPolicy.evaluate(input), decision: "meta_review_required", reasons: ["complex_contract"] }) }
  const f = fixture(policy)
  await f.host.openRun({ sessionID: "s", workspace: ".", goal: "fixture" })
  const result = await f.host.proposeContract("s", proposal())
  expect(f.reviewed()).toBe(1)
  expect(f.proposed()).toBe(1)
  expect(result.planningState).toBe("executing")
})

test("structural failures never become policy questions, and policy errors fail closed", async () => {
  let calls = 0
  const f = fixture({ evaluate: () => { calls++; throw new Error("policy unavailable") } })
  await f.host.openRun({ sessionID: "s", workspace: ".", goal: "fixture" })
  const invalid = proposal(); invalid.claims[0]!.criterionIds = ["unknown"]
  await expect(f.host.proposeContract("s", invalid)).rejects.toThrow("CONTRACT_BINDING")
  expect(calls).toBe(0)
  await expect(f.host.proposeContract("s", proposal())).rejects.toThrow("policy unavailable")
  expect(calls).toBe(1)
  expect(f.proposed()).toBe(0)
  expect(f.host.status("s").planningState).not.toBe("awaiting_input")
  expect(() => f.host.assertToolAllowed("s", "write")).toThrow()
})
