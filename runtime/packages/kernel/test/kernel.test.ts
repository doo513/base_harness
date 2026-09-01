import { describe, expect, test } from "bun:test"
import {
  allowsOperation,
  applyControl,
  createKernelSessionState,
  decidePlanning,
  parseMetaReview,
  validatePlanSpec,
  type PlanSpec,
} from "../src"

describe("kernel", () => {
  test("plans only when typed signals require it", () => {
    const state = createKernelSessionState()
    expect(
      decidePlanning(state, {
        risk: "low",
        requiredClaimCount: 1,
        requiredCriterionCount: 1,
        targetCount: 1,
        hasExternalClaim: false,
        applicabilityResolved: true,
        requiredEvidenceFamilyCount: 1,
      }),
    ).toBe("direct")
    expect(decidePlanning(applyControl(state, { type: "skill.set", skill: "hackathon", enabled: true }), {
      risk: "low",
      requiredClaimCount: 1,
      requiredCriterionCount: 1,
      targetCount: 1,
      hasExternalClaim: false,
      applicabilityResolved: true,
      requiredEvidenceFamilyCount: 1,
    })).toBe("planned")
  })

  test("general domain is read-only", () => {
    const state = applyControl(createKernelSessionState(), { type: "domain.set", domain: "general" })
    expect(allowsOperation(state, "read")).toBe(true)
    expect(allowsOperation(state, "mutate")).toBe(false)
    expect(allowsOperation(state, "delegate", "explore")).toBe(true)
    expect(allowsOperation(state, "delegate", "general")).toBe(false)
  })

  test("rejects blocking pass and cyclic plans", () => {
    expect(() => parseMetaReview({
      phase: "goal_contract",
      outcome: "pass",
      issues: [{
        id: "i1",
        kind: "ambiguity",
        severity: "blocking",
        targetIds: [],
        sourceRefs: [],
        statement: "ambiguous",
      }],
    }, "goal_contract")).toThrow()
    const plan = {
      schemaVersion: "plan-v1",
      planId: "p1",
      revision: 1,
      runId: "r1",
      domain: "develop",
      skills: [],
      goalContractId: "g1",
      goalContractRevision: 1,
      goalContractHash: "hash",
      basis: [],
      assumptions: [],
      steps: [
        { id: "a", title: "a", claimIds: ["c"], criterionIds: ["k"], dependsOn: ["b"], readSet: [], writeSet: [], priority: "required" },
        { id: "b", title: "b", claimIds: ["c"], criterionIds: ["k"], dependsOn: ["a"], readSet: [], writeSet: [], priority: "required" },
      ],
    } satisfies PlanSpec
    expect(() => validatePlanSpec(plan)).toThrow("PLAN_CYCLE")
  })
})
