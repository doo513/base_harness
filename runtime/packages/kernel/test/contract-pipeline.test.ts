import { expect, test } from "bun:test"
import type { ContractSubmission, DomainPolicySnapshot } from "@base-harness/domain-contracts"
import { prepareContract, scanContract, validateContract, dedupeContractDiagnostics } from "../src"

export const policy: DomainPolicySnapshot = {
  domainId: "fixture", domainRevision: "1", skillRevisions: [], allowedOperations: ["read"], allowedSubagentTypes: [],
  requiresPlan: false, demoFirst: false,
  verification: { defaultStrength: "structural", criterionTemplates: ["observable"] },
  measurement: { summarySchemaVersion: "evidence-summary-v1", requiredFields: [] },
}

export function submission(): ContractSubmission {
  return {
    goal: "Write the requested file", constraints: [],
    criteria: [{ criterionId: "k", statement: "The file exists", required: true, risk: "low", claimIds: ["c"] }],
    claims: [{ claimId: "c", criterionIds: ["k"], origin: "user", kind: "artifact", statement: "The file exists",
      scope: { targets: ["result.txt"], capabilities: ["write"], exclusions: [] }, applicability: {},
      predicate: { type: "exists" }, verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 } }],
    interpretation: { version: 1, candidates: [] },
  }
}

const check = (value: unknown) => validateContract(scanContract(prepareContract(value, policy, "adaptive")))

test("Prepare copies nested input and policy; each stage exposes independent data and no authority", () => {
  const input = submission(), selected = structuredClone(policy)
  const original = structuredClone(input)
  const prepared = prepareContract(input, selected, "adaptive")
  expect(input).toEqual(original)
  input.claims[0]!.scope.targets.push("injected")
  selected.verification.criterionTemplates.push("injected")
  expect(prepared.body.claims[0]!.scope.targets).toEqual(["result.txt"])
  expect(prepared.policy.verification.criterionTemplates).toEqual(["observable"])
  const scanned = scanContract(prepared)
  expect(scanned.links).toEqual([{ from: "c", to: "k", fromKind: "claim" }, { from: "k", to: "c", fromKind: "criterion" }])
  const checked = validateContract(scanned)
  scanned.body.claims[0]!.scope.targets.push("later")
  expect(checked.valid).toBe(true)
  if (checked.valid) expect(checked.candidate.body.claims[0]!.scope.targets).toEqual(["result.txt"])
  expect(checked).not.toHaveProperty("mutatingActionAllowed")
  expect(checked).not.toHaveProperty("ready")
})

for (const [name, mutate, code] of [
  ["empty goal", (s: ContractSubmission) => { s.goal = " " }, "CONTRACT_GOAL"],
  ["empty ID", (s: ContractSubmission) => { s.claims[0]!.claimId = " " }, "CONTRACT_CLAIM_ID"],
  ["duplicate ID", (s: ContractSubmission) => { s.claims.push(structuredClone(s.claims[0]!)) }, "CONTRACT_CLAIM_ID"],
  ["missing statement", (s: ContractSubmission) => { s.criteria[0]!.statement = "" }, "CONTRACT_CRITERION_REQUIRED"],
  ["empty scope", (s: ContractSubmission) => { s.claims[0]!.scope.targets = [] }, "CONTRACT_CLAIM_REQUIRED"],
  ["unknown claim", (s: ContractSubmission) => { s.criteria[0]!.claimIds = ["outside"] }, "CONTRACT_BINDING"],
  ["reverse reference", (s: ContractSubmission) => { s.claims[0]!.criterionIds = [] }, "CONTRACT_BINDING"],
  ["duplicate reference", (s: ContractSubmission) => { s.criteria[0]!.claimIds.push("c") }, "CONTRACT_DUPLICATE_REFERENCE"],
  ["unknown template", (s: ContractSubmission) => { s.criteria[0]!.verificationTemplate = "outside" }, "DOMAIN_CRITERION_TEMPLATE"],
] as const) test(`Validate rejects ${name} without review`, () => {
  const input = submission(); mutate(input)
  const result = check(input)
  expect(result.valid).toBe(false)
  expect(result.diagnostics.map((issue) => issue.code)).toContain(code)
  expect(result).not.toHaveProperty("candidate")
})

test("unbound interpretation diagnostics retain all sources and targets when deduplicated", () => {
  const input = submission()
  input.interpretation.candidates = ["first", "second"].map((id) => ({
    id, kind: "missing_decision", impact: "scope", statement: "Select a scope",
    sourceRefs: [{ source: id }], affectedClaimIds: [id], affectedCriterionIds: ["k"],
  }))
  const scanned = scanContract(prepareContract(input, policy, "adaptive"))
  expect(scanned.interpretation.candidates).toHaveLength(2)
  const checked = validateContract(scanned)
  expect(checked.valid).toBe(false)
  expect(checked.diagnostics).toMatchObject([{
    code: "INTERPRETATION_UNKNOWN_CLAIM", issueIds: ["first", "second"],
    affectedClaimIds: ["first", "second"], sourceRefs: [{ source: "first" }, { source: "second" }],
  }])
  expect(dedupeContractDiagnostics(checked.diagnostics)).toEqual(checked.diagnostics)
})

test("submissions cannot carry Host answers or cross-session context", () => {
  for (const key of ["answers", "accepted", "sessionID", "runId", "mutatingActionAllowed"]) {
    expect(() => check({ ...submission(), [key]: "actor supplied" })).toThrow("CONTRACT_SUBMISSION_FIELD")
  }
})
