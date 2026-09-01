import { describe, expect, test } from "bun:test"
import {
  decideContractPreflight,
  parseInterpretationProposal,
  validateInterpretationBindings,
  type ContractPreflightSignals,
} from "../src"

const signals: ContractPreflightSignals = {
  risk: "low",
  configuredProfile: "adaptive",
  requiredClaimCount: 1,
  requiredCriterionCount: 1,
  hasExternalClaim: false,
  applicabilityResolved: true,
}

describe("selective contract preflight", () => {
  test("accepts an atomic implementation choice without meta review", () => {
    const interpretation = parseInterpretationProposal({
      version: 1,
      candidates: [
        {
          id: "u1",
          kind: "assumption",
          impact: "implementation_choice",
          affectedClaimIds: ["claim-1"],
          affectedCriterionIds: [],
          sourceRefs: [{ source: "user_prompt", pointer: "request" }],
          statement: "The private helper name is not prescribed.",
        },
      ],
    })
    validateInterpretationBindings(interpretation, ["claim-1"], ["criterion-1"])
    expect(decideContractPreflight(interpretation, signals).decision).toBe("accept")
  })

  test("requires input for a consequential ambiguity", () => {
    const interpretation = parseInterpretationProposal({
      version: 1,
      candidates: [
        {
          id: "u1",
          kind: "multiple_interpretations",
          impact: "user_preference",
          affectedClaimIds: ["claim-1"],
          affectedCriterionIds: ["criterion-1"],
          sourceRefs: [{ source: "user_prompt", pointer: "format" }],
          statement: "Two user-visible formats are equally plausible.",
        },
      ],
    })
    const result = decideContractPreflight(interpretation, signals)
    expect(result.decision).toBe("needs_input")
    expect(result.mutatingActionAllowed).toBe(false)
  })

  test("requires meta review for high risk and strict profiles", () => {
    expect(decideContractPreflight({ version: 1, candidates: [] }, { ...signals, risk: "high" }).decision).toBe(
      "meta_review_required",
    )
    expect(
      decideContractPreflight(
        { version: 1, candidates: [] },
        { ...signals, configuredProfile: "strict" },
      ).decision,
    ).toBe("meta_review_required")
  })

  test("rejects references outside the normalized contract", () => {
    const interpretation = parseInterpretationProposal({
      version: 1,
      candidates: [
        {
          id: "u1",
          kind: "conflict",
          impact: "scope",
          affectedClaimIds: ["missing"],
          affectedCriterionIds: [],
          sourceRefs: [{ source: "user_prompt" }],
          statement: "Scope conflicts.",
        },
      ],
    })
    expect(() => validateInterpretationBindings(interpretation, ["claim-1"], ["criterion-1"])).toThrow(
      "INTERPRETATION_UNKNOWN_CLAIM",
    )
  })

  test("keeps selective review below always-review without skipping deterministic blockers", () => {
    const fixtures = [
      { version: 1 as const, candidates: [] },
      { version: 1 as const, candidates: [] },
      { version: 1 as const, candidates: [] },
    ]
    const fixtureSignals: ContractPreflightSignals[] = [
      signals,
      { ...signals, risk: "high" },
      { ...signals, requiredClaimCount: 2 },
    ]
    const selectiveCalls = fixtures.filter(
      (fixture, index) =>
        decideContractPreflight(fixture, fixtureSignals[index]!).decision === "meta_review_required",
    ).length
    expect({ deterministicOnlyCalls: 0, selectiveCalls, alwaysReviewCalls: fixtures.length }).toEqual({
      deterministicOnlyCalls: 0,
      selectiveCalls: 2,
      alwaysReviewCalls: 3,
    })
  })
})
