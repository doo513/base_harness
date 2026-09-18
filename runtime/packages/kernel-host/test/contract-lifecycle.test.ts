import { expect, test } from "bun:test"
import type { ContractQuestionBatch, ContractSubmission } from "@base-harness/domain-contracts"
import { KernelHost } from "../src"
import { contractFixture } from "./contract-fixture"

function proposal(count = 0, high = false): ContractSubmission {
  return contractFixture({
    goal: "Produce a report",
    criteria: [{ criterionId: "k", claimIds: ["c"], risk: high ? "high" : "low" }],
    claims: [{ claimId: "c", criterionIds: ["k"], applicability: {} }],
    interpretation: { version: 1, candidates: Array.from({ length: count }, (_, i) => ({
      id: `u${i}`, kind: "missing_decision", impact: "user_preference", statement: `Choose option ${i}`,
      affectedClaimIds: ["c"], affectedCriterionIds: ["k"], sourceRefs: [{ source: "user_prompt", pointer: `item${i}` }],
    })) },
  })
}
function fixture(accept = true) {
  let serial = 0
  const current = new Map<string, any>(), proposed: any[] = [], failures: any[] = []
  const host = new KernelHost({
    openRun: async ({ sessionID }) => { const status = { sessionID, runId: `run${++serial}`, phase: "planning" }; current.set(sessionID, status); return status },
    status: (sessionID) => current.get(sessionID) ?? { sessionID, phase: "inactive" },
    proposeContract: async (sessionID, candidate) => { proposed.push(candidate); const status = { ...current.get(sessionID), contractStatus: accept ? "accepted" : "rejected" }; current.set(sessionID, status); return status },
    acceptWorkGraph: async () => ({}),
    reportMetaReviewFailure: async (_session, error, _phase, source) => { failures.push({ error, source }) },
  })
  return { host, proposed, current, failures, open: (sessionID = "s") => host.openRun({ sessionID, workspace: "/fixture", goal: "original user request" }) }
}
const blocking = { id: "review-issue", kind: "ambiguity", severity: "blocking", targetIds: ["k"], sourceRefs: [{ source: "request" }], statement: "Specify the output" }
const pass = { phase: "goal_contract", outcome: "pass", issues: [] }
function denied(host: KernelHost, session = "s") {
  expect(() => host.assertToolAllowed(session, "write")).toThrow()
  expect(host.canVerifyRoot(session)).toBe(false)
}

test("seven decisions are asked in 3/3/1 batches, recorded per issue, and still require a new candidate", async () => {
  const f = fixture(); await f.open()
  await f.host.proposeContract("s", proposal(7))
  const batches: ContractQuestionBatch[] = []
  const status = await f.host.requestContractQuestions("s", async (batch) => {
    batches.push(batch); denied(f.host)
    return batch.issues.map(() => ["Apply suggestion"])
  })
  expect(batches.map((batch) => batch.issues.length)).toEqual([3, 3, 1])
  expect(new Set(batches.map((batch) => batch.id)).size).toBe(3)
  expect(batches.every((batch) => batch.sessionID === "s" && batch.runId === "run1" && batch.candidateRevision === 1)).toBe(true)
  expect(status.contractProcessing).toMatchObject({ outcome: "revision_required", candidateRevision: 1 })
  expect(status.contractProcessing.answers).toHaveLength(7)
  expect(status.contractProcessing.issues).toHaveLength(7)
  expect(status.planningState).toBe("contract_building")
  expect(f.proposed).toHaveLength(0); denied(f.host)
  const accepted = await f.host.proposeContract("s", proposal())
  expect(accepted.contractProcessing).toMatchObject({ outcome: "accepted", candidateRevision: 2, answers: [] })
  expect(f.proposed).toHaveLength(1)
})

for (const [label, response] of [["cancel", undefined], ["empty", []], ["blank", [[" "]]], ["no option", [[]]]] as const) {
  test(`question ${label} does not resolve or authorize`, async () => {
    const f = fixture(); await f.open(); await f.host.proposeContract("s", proposal(1))
    const status = await f.host.requestContractQuestions("s", async () => response)
    expect(status.contractProcessing).toMatchObject({ outcome: "needs_input", answers: [] })
    expect(status.planningState).toBe("awaiting_input"); denied(f.host)
    expect(f.proposed).toHaveLength(0)
  })
}

for (const change of ["revision", "run"] as const) test(`an answer to an old ${change} cannot affect the current candidate`, async () => {
  const f = fixture(); await f.open(); await f.host.proposeContract("s", proposal(1))
  let answer!: (value: string[][]) => void, started!: () => void
  const ready = new Promise<void>((resolve) => { started = resolve })
  const pending = f.host.requestContractQuestions("s", () => { started(); return new Promise((resolve) => { answer = resolve }) })
  await ready
  if (change === "run") await f.open()
  await f.host.proposeContract("s", proposal(1))
  answer([["yes"]])
  await expect(pending).rejects.toThrow("CONTRACT_ANSWER_STALE")
  expect(f.host.status("s").contractProcessing.answers).toEqual([]); denied(f.host)
})

test("question binding is Host-owned and cannot be redirected to another session", async () => {
  const f = fixture(); await f.open("s"); await f.open("other")
  await f.host.proposeContract("s", proposal(1)); await f.host.proposeContract("other", proposal(1))
  const status = await f.host.requestContractQuestions("s", async (batch) => {
    batch.sessionID = "other"; batch.runId = "run2"; batch.issues[0]!.id = "forged"
    return [["chosen format"]]
  })
  expect(status.contractProcessing.answers[0].issueId).toBe("interpretation:u0")
  expect(status.contractProcessing.questions[0].sessionID).toBe("s")
  expect(f.host.status("other").contractProcessing.answers).toEqual([])
  denied(f.host, "s"); denied(f.host, "other")
})

test("revise is a contract revision requirement, never a user question", async () => {
  const f = fixture(); await f.open()
  f.host.registerMetaReviewer(async () => ({ phase: "goal_contract", outcome: "revise", issues: [blocking] }))
  const status = await f.host.proposeContract("s", proposal(0, true))
  expect(status.planningState).toBe("contract_building")
  expect(status.contractProcessing.outcome).toBe("revision_required")
  await f.host.requestContractQuestions("s", async () => { throw new Error("must not ask") })
  expect(f.proposed).toHaveLength(0); denied(f.host)
})

test("review needs_input creates a bound question without contract acceptance", async () => {
  const f = fixture(); await f.open()
  f.host.registerMetaReviewer(async () => ({ phase: "goal_contract", outcome: "needs_input", issues: [blocking] }))
  await f.host.proposeContract("s", proposal(0, true))
  const status = await f.host.requestContractQuestions("s", async (batch) => {
    expect(batch.issues[0]).toMatchObject({ id: "review:review-issue", affectedCriterionIds: ["k"] })
    return [["Keep requirement"]]
  })
  expect(status.contractProcessing.outcome).toBe("revision_required")
  expect(f.proposed).toHaveLength(0); denied(f.host)
})

test("a revised full candidate is checked before the second review and Runtime accepts the final body", async () => {
  const f = fixture(); await f.open(); let calls = 0
  const changed = proposal(0, true); changed.goal = "A corrected goal"
  f.host.registerMetaReviewer(async (request) => {
    calls++
    expect(request.contractContext?.originalRequest).toBe("original user request")
    if (calls === 1) return { phase: "goal_contract", outcome: "revise", issues: [blocking], revisedArtifact: changed }
    expect((request.artifact as ContractSubmission).goal).toBe(changed.goal)
    expect(request.contractContext?.candidateRevision).toBe(2)
    return pass
  })
  const status = await f.host.proposeContract("s", proposal(0, true))
  expect(calls).toBe(2); expect(f.proposed[0].goal).toBe(changed.goal)
  expect(status.preflight.reviewerCallCount).toBe(2)
})

for (const outcome of ["pass", "revise"] as const) test(`${outcome} cannot carry a structurally invalid replacement`, async () => {
  const f = fixture(); await f.open(); let calls = 0
  const changed = proposal(0, true); changed.criteria[0]!.claimIds = ["outside"]
  f.host.registerMetaReviewer(async () => { calls++; return { phase: "goal_contract", outcome, issues: outcome === "pass" ? [] : [blocking], revisedArtifact: changed } })
  await expect(f.host.proposeContract("s", proposal(0, true))).rejects.toThrow("CONTRACT_BINDING")
  expect(calls).toBe(1); expect(f.proposed).toHaveLength(0)
  expect(f.host.status("s").contractProcessing.outcome).toBe("error"); denied(f.host)
})

test("review pass and past acceptance cannot bypass Runtime rejection or revalidation", async () => {
  const f = fixture(false); await f.open(); f.host.registerMetaReviewer(async () => pass)
  const rejected = await f.host.proposeContract("s", proposal(0, true))
  expect(rejected.contractProcessing.outcome).toBe("rejected"); denied(f.host)
  const good = fixture(); await good.open(); await good.host.proposeContract("s", proposal())
  expect(good.host.hasAcceptedContract("s")).toBe(true)
  const malformed = proposal(); malformed.goal = " "
  await expect(good.host.proposeContract("s", malformed)).rejects.toThrow("CONTRACT_GOAL")
  const view = good.host.status("s"); view.preflight.mutatingActionAllowed = true
  expect(good.host.hasAcceptedContract("s")).toBe(false); denied(good.host)
  await expect(good.host.acceptWorkGraph("s", {})).rejects.toThrow("CONTRACT_REQUIRED")
})

test("a Question service failure is an error, while a duplicate ask cannot cancel the active batch", async () => {
  const f = fixture(); await f.open(); await f.host.proposeContract("s", proposal(1))
  let answer!: (value: undefined) => void, started!: () => void
  const ready = new Promise<void>((resolve) => { started = resolve })
  const pending = f.host.requestContractQuestions("s", () => { started(); return new Promise((resolve) => { answer = resolve }) })
  await ready
  await expect(f.host.requestContractQuestions("s", async () => [])).rejects.toThrow("CONTRACT_QUESTION_ACTIVE")
  expect(f.host.status("s").contractProcessing.outcome).toBe("needs_input")
  answer(undefined); await pending
  await expect(f.host.requestContractQuestions("s", async () => { throw new Error("service unavailable") })).rejects.toThrow("service unavailable")
  expect(f.host.status("s").contractProcessing.outcome).toBe("error")
  expect(f.host.status("s").planningState).toBe("contract_building"); denied(f.host)
})

test("review pass remains non-mutating while Runtime acceptance is pending", async () => {
  let accept!: (value: any) => void, called!: () => void
  const ready = new Promise<void>((resolve) => { called = resolve })
  const current = { sessionID: "s", runId: "run", phase: "planning" }
  const host = new KernelHost({
    openRun: async () => current, status: () => current, acceptWorkGraph: async () => ({}),
    proposeContract: async () => { called(); return new Promise((resolve) => { accept = resolve }) },
  })
  await host.openRun({ sessionID: "s", workspace: "/fixture", goal: "fixture" })
  host.registerMetaReviewer(async () => pass)
  const pending = host.proposeContract("s", proposal(0, true))
  await ready
  expect(host.status("s").contractProcessing.outcome).toBe("awaiting_runtime"); denied(host)
  await expect(host.proposeContract("s", proposal())).rejects.toThrow("CONTRACT_PROCESSING_ACTIVE")
  accept({ ...current, contractStatus: "accepted" }); await pending
  expect(host.hasAcceptedContract("s")).toBe(true)
})

for (const cancellation of ["run", "tool"] as const) test(`a late answer after ${cancellation} cancellation is never recorded`, async () => {
  const f = fixture(); await f.open(); await f.host.proposeContract("s", proposal(1))
  const controller = new AbortController()
  let answer!: (value: string[][]) => void, started!: () => void
  const ready = new Promise<void>((resolve) => { started = resolve })
  const pending = f.host.requestContractQuestions("s", () => {
    started(); return new Promise((resolve) => { answer = resolve })
  }, controller.signal)
  await ready
  if (cancellation === "run") f.current.get("s").phase = "interrupted"
  else controller.abort()
  answer([["Apply suggestion"]])
  await expect(pending).rejects.toThrow("CONTRACT_ANSWER_STALE")
  expect(f.host.status("s").contractProcessing.answers).toEqual([])
  expect(f.host.status("s").contractProcessing.questions[0].status).toBe("cancelled")
  expect(f.host.hasAcceptedContract("s")).toBe(false)
  expect(f.proposed).toHaveLength(0)
})

test("review receives only Host-recorded clarifications from the current Run", async () => {
  const f = fixture(); await f.open(); await f.host.proposeContract("s", proposal(1))
  await f.host.requestContractQuestions("s", async () => [["Use CSV"]])
  let prior = true
  f.host.registerMetaReviewer(async (request) => {
    const clarifications = request.contractClarifications!
    expect(clarifications).toHaveLength(prior ? 1 : 0)
    if (prior) {
      expect(clarifications[0]).toMatchObject({ sessionID: "s", runId: "run1", candidateRevision: 1 })
      expect(clarifications[0]!.questions[0]!.issues[0]!.id).toBe("interpretation:u0")
      expect(clarifications[0]!.answers[0]!.answer).toEqual(["Use CSV"])
      clarifications[0]!.answers[0]!.answer[0] = "mutated by reviewer"
    }
    return pass
  })
  await f.host.proposeContract("s", proposal(0, true))
  // The reviewer's edit to its request cannot change recorded clarification.
  await f.host.proposeContract("s", proposal(0, true))
  await f.open()
  prior = false
  await f.host.proposeContract("s", proposal(0, true))
})

test("partially answered batches preserve the unanswered issues for the next question request", async () => {
  const f = fixture(); await f.open(); await f.host.proposeContract("s", proposal(4))
  const partial = await f.host.requestContractQuestions("s", async (batch) => {
    expect(batch.issues.map((issue) => issue.id)).toEqual(["interpretation:u0", "interpretation:u1", "interpretation:u2"])
    return [["CSV"], [], ["UTC"]]
  })
  expect(partial.contractProcessing).toMatchObject({ outcome: "needs_input" })
  expect(partial.contractProcessing.answers).toHaveLength(2)
  expect(partial.contractProcessing.questions[0].status).toBe("partial")
  const completed = await f.host.requestContractQuestions("s", async (batch) => {
    expect(batch.issues.map((issue) => issue.id)).toEqual(["interpretation:u1", "interpretation:u3"])
    return [["UTF-8"], ["Include headings"]]
  })
  expect(completed.contractProcessing).toMatchObject({ outcome: "revision_required" })
  expect(completed.contractProcessing.answers).toHaveLength(4)
  expect(f.proposed).toHaveLength(0); denied(f.host)
})
