import { expect, spyOn } from "bun:test"
import { Effect, Exit, Fiber, Queue } from "effect"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { KernelHost } from "@base-harness/kernel-host"
import type { ContractSubmission } from "@base-harness/domain-contracts"
import { HarnessContractTool } from "../../src/tool/harness-contract"
import { Question } from "../../src/question"
import { Agent } from "../../src/agent/agent"
import { Truncate } from "../../src/tool/truncate"
import { EventV2Bridge } from "../../src/event-v2-bridge"
import { SessionID, MessageID } from "../../src/session/schema"
import { TestInstance } from "../fixture/fixture"
import { testEffect } from "../lib/effect"

const it = testEffect(LayerNode.compile(LayerNode.group([Question.node, EventV2Bridge.node, Truncate.node, Agent.node])))

for (const mode of ["answers", "dismiss", "abort"] as const) it.instance(`harness_contract records only real Question service ${mode}`, () => Effect.gen(function* () {
  const cancelled = mode !== "answers"
  const abort = new AbortController()
  const sessionID = SessionID.make("ses_contract-" + crypto.randomUUID())
  const current = { sessionID, runId: "run-" + sessionID, phase: "planning" }
  let accepted = 0
  const host = new KernelHost({
    openRun: async () => current, status: () => current,
    proposeContract: async () => { accepted++; return { ...current, contractStatus: "accepted" } },
    acceptWorkGraph: async () => current,
  })
  const propose = host.proposeContract.bind(host), questions = host.requestContractQuestions.bind(host)
  const submitSpy = spyOn(KernelHost.prototype, "proposeContract").mockImplementation(propose)
  const questionSpy = spyOn(KernelHost.prototype, "requestContractQuestions").mockImplementation(questions)
  yield* Effect.addFinalizer(() => Effect.sync(() => { submitSpy.mockRestore(); questionSpy.mockRestore() }))
  const workspace = (yield* TestInstance).directory
  yield* Effect.promise(() => host.openRun({ sessionID, workspace, goal: "Select a format" }))
  const proposal: ContractSubmission = {
    goal: "Select a format",
    criteria: [{ criterionId: "k", statement: "A report exists", claimIds: ["c"], required: true, risk: "low" }],
    claims: [{ claimId: "c", statement: "A report exists", criterionIds: ["k"], origin: "user", kind: "artifact",
      scope: { targets: ["report.txt"], capabilities: ["write"], exclusions: [] }, applicability: {}, predicate: { type: "exists" },
      verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 } }],
    interpretation: { version: 1, candidates: Array.from({ length: cancelled ? 1 : 4 }, (_, i) => ({
      id: `u${i}`, kind: "missing_decision", impact: "user_preference", statement: `Select format ${i}`,
      affectedClaimIds: ["c"], affectedCriterionIds: ["k"], sourceRefs: [{ source: "request" }],
    })) },
  }
  const question = yield* Question.Service, events = yield* EventV2Bridge.Service
  const asked = yield* Queue.unbounded<void>()
  const off = yield* events.listen((event) => {
    if (event.type === Question.Event.Asked.type) Queue.offerUnsafe(asked, undefined)
    return Effect.void
  })
  yield* Effect.addFinalizer(() => off)
  const tool = yield* (yield* HarnessContractTool).init()
  const fiber = yield* tool.execute(proposal, {
    sessionID, messageID: MessageID.make("msg_contract"), callID: "call", agent: "build", messages: [],
    abort: abort.signal, metadata: () => Effect.void, ask: () => Effect.void,
  }).pipe(Effect.forkScoped)
  const counts: number[] = []
  for (let batch = 0; batch < (cancelled ? 1 : 2); batch++) {
    let request: Question.Request | undefined
    while (!(request = (yield* question.list())[0])) yield* Queue.take(asked).pipe(Effect.timeout("5 seconds"))
    expect(request.sessionID).toBe(sessionID)
    counts.push(request.questions.length)
    if (mode === "abort") abort.abort()
    else if (cancelled) yield* question.reject(request.id)
    else yield* question.reply({ requestID: request.id, answers: request.questions.map(() => ["A custom answer"]) })
  }
  let result: any
  if (mode === "abort") {
    expect(Exit.isFailure(yield* Fiber.await(fiber))).toBe(true)
    const kernel = host.status(sessionID)
    result = { kernel, answers: kernel.contractProcessing.answers }
    expect(kernel.contractProcessing.questions[0].status).toBe("cancelled")
  } else result = JSON.parse((yield* Fiber.join(fiber)).output)
  expect(counts).toEqual(cancelled ? [1] : [3, 1])
  expect(result.kernel.contractProcessing.outcome).toBe(cancelled ? "needs_input" : "revision_required")
  expect(result.answers).toHaveLength(cancelled ? 0 : 4)
  expect(accepted).toBe(0)
  expect(() => host.assertToolAllowed(sessionID, "write")).toThrow()
  expect(yield* question.list()).toEqual([])
}), 30000)
