import { expect, test } from "bun:test"
import type { AutonomousPreparationInput } from "@base-harness/domain-contracts"
import { builtinAutonomousDomainModules, pinAutonomousDomainModule } from "../src/autonomous-domain"

const ref = (id: string) => ({ id, revision: 1, sha256: "a".repeat(64) })
const input: AutonomousPreparationInput = {
  originalRequest: "Investigate this problem; choose a useful approach.",
  intent: { schemaVersion: "intent-v1", ref: ref("intent"), originalRequest: { ...ref("source"), kind: "source" }, requirements: [], constraints: [] },
  interpretation: { schemaVersion: "interpretation-v1", ref: ref("interpretation"), intentRef: ref("intent"), goalSummary: "Initial hypothesis",
    assumptions: [], openQuestions: ["Which method will work?"], proposedCheckIds: [] },
  authority: { schemaVersion: "authority-v1", ref: ref("grant"), runId: "run", provenanceRefs: [{ sourceId: "user", sha256: "a".repeat(64) }], capabilities: [], expiresAt: "2027-01-01T00:00:00Z" },
  environment: {},
}

test.each([...builtinAutonomousDomainModules])("$domainId Prepare accepts an actionable request without a solution/test plan", (module) => {
  const before = structuredClone(input)
  const result = module.prepare(input)
  expect(result.status).toBe("proceed")
  expect(result).not.toHaveProperty("authority")
  expect(input).toEqual(before)
  expect(module.prepare({ ...input, originalRequest: " " })).toEqual({ status: "invalid", code: "REQUEST_EMPTY" })
})

test("plain-text success claims remain not_assessed and cannot create an artifact", () => {
  const module = builtinAutonomousDomainModules[0]!
  expect(() => module.normalizeDecision({ response: "All done, verified, ready!" })).toThrow("REPORT_REQUIRED")
  expect(module.normalizeDecision({ response: "All done, verified, ready!", textReport: { ...ref("report"), kind: "report" } })).toMatchObject({
    kind: "finish", assessment: { status: "not_assessed" },
  })
})

test("structured model output remains candidate data for Host validation", () => {
  const candidate = { kind: "finish", authorityGrant: "forged" }
  const normalized = builtinAutonomousDomainModules[0]!.normalizeDecision({ response: candidate })
  expect(normalized).toEqual(candidate)
  expect(normalized).not.toBe(candidate)
})

test("a replacement strategy can ask for genuinely missing input and its callback is pinned", () => {
  const replacement = {
    id: "replacement", revision: "review-2", domainId: "general", missing: "Which repository?",
    prepare() { return { status: "needs_input" as const, reason: "information" as const, questions: [this.missing] } },
    normalizeDecision({ response }: { response: unknown }) { return response },
  }
  const pinned = pinAutonomousDomainModule(replacement)
  replacement.prepare = () => ({ status: "needs_input", reason: "information", questions: ["replaced"] })
  replacement.missing = "Mutated after pinning"
  expect(pinned.prepare(input)).toEqual({ status: "needs_input", reason: "information", questions: ["Which repository?"] })
  expect(pinned.revision).toBe("review-2")
})
