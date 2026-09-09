import { expect, test } from "bun:test"
import { KernelHost } from "../src"

function fixture() {
  const failures: Array<{ error: any; source?: string }> = []
  let accepted = 0
  const host = new KernelHost({
    openRun: async () => ({ runId: "run", phase: "planning" }),
    status: () => ({ runId: "run", phase: "planning" }),
    proposeContract: async () => { accepted++; return { runId: "run", contractStatus: "accepted" } },
    acceptWorkGraph: async () => { throw new Error("No worker dispatch during this fixture") },
    reportMetaReviewFailure: async (_sessionID, error, _phase, source) => { failures.push({ error, source }) },
  })
  const proposal = {
    goal: "Inspect a high-risk contract", interpretation: { version: 1, candidates: [] },
    criteria: [{ criterionId: "criterion", statement: "Inspect", claimIds: ["claim"], required: true, risk: "high" }],
    claims: [{ claimId: "claim", criterionIds: ["criterion"], statement: "Inspect",
      scope: { targets: ["input.txt"] }, applicability: {}, verifierPolicy: { minIndependentFamilies: 1 } }],
  }
  return { host, proposal, failures, accepted: () => accepted }
}

test("Host dispatch exceptions are not retried or reclassified as malformed model JSON", async () => {
  const { host, proposal, failures, accepted } = fixture()
  const cause = Object.assign(new Error("Host phase rejected the review"), { code: "PHASE_VIOLATION" })
  let calls = 0
  host.registerMetaReviewer(async () => { calls++; throw cause })
  await host.openRun({ sessionID: "root", workspace: "/fixture", goal: proposal.goal })
  const error = await host.proposeContract("root", proposal).then(() => null, error => error)
  expect(error).toBe(cause)
  expect(calls).toBe(1)
  expect(failures).toEqual([{ error: cause, source: "harness" }])
  expect(accepted()).toBe(0)
  expect(() => host.assertToolAllowed("root", "write")).toThrow()
})

test("malformed model output gets one schema repair then a typed protocol failure", async () => {
  const { host, proposal, failures, accepted } = fixture()
  let calls = 0
  host.registerMetaReviewer(async () => { calls++; return "not a typed review" })
  await host.openRun({ sessionID: "root", workspace: "/fixture", goal: proposal.goal })
  await expect(host.proposeContract("root", proposal)).rejects.toMatchObject({ code: "META_REVIEW_MODEL_PROTOCOL" })
  expect(calls).toBe(2)
  expect(failures).toMatchObject([{ source: "model", error: { name: "InvalidProviderOutput", code: "META_REVIEW_MODEL_PROTOCOL" } }])
  expect(accepted()).toBe(0)
})

test("one successful schema repair accepts the contract without manufacturing evidence", async () => {
  const { host, proposal, failures, accepted } = fixture()
  let calls = 0
  host.registerMetaReviewer(async request => ++calls === 1 ? "bad JSON" : { phase: request.phase, outcome: "pass", issues: [] })
  await host.openRun({ sessionID: "root", workspace: "/fixture", goal: proposal.goal })
  const status = await host.proposeContract("root", proposal)
  expect(calls).toBe(2)
  expect(accepted()).toBe(1)
  expect(failures).toEqual([])
  expect(status.preflight.reviewerCallCount).toBe(2)
  expect(status.outcome).not.toBe("ready")
  expect(status.evidenceRefs).toBeUndefined()
})

test("a missing reviewer is a Host failure without contract acceptance", async () => {
  const { host, proposal, failures, accepted } = fixture()
  await host.openRun({ sessionID: "root", workspace: "/fixture", goal: proposal.goal })
  await expect(host.proposeContract("root", proposal)).rejects.toMatchObject({ code: "META_REVIEWER_UNAVAILABLE" })
  expect(failures).toMatchObject([{ source: "harness", error: { code: "META_REVIEWER_UNAVAILABLE" } }])
  expect(accepted()).toBe(0)
})
