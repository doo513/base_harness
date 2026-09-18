import { expect } from "bun:test"
import { Effect, Exit, Fiber, Queue } from "effect"
import { join } from "node:path"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { CoordinatorRuntime, RunRepository } from "@base-harness/coordinator"
import { builtinAutonomousDomainModules } from "@base-harness/domain"
import { KernelHost } from "@base-harness/kernel-host"
import { askAutonomousQuestions } from "../../src/harness/autonomous-question"
import { captureExecutionContext } from "../../src/harness/execution-context"
import { Question } from "../../src/question"
import { SessionID } from "../../src/session/schema"
import { EventV2Bridge } from "../../src/event-v2-bridge"
import { TestInstance } from "../fixture/fixture"
import { testEffect } from "../lib/effect"

const it = testEffect(LayerNode.compile(LayerNode.group([Question.node, EventV2Bridge.node])))

for (const mode of ["answers", "dismiss", "abort"] as const) it.instance(`autonomous Host uses real Question service: ${mode}`, () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const sessionID = SessionID.make("ses_autonomous_question")
  const context = yield* captureExecutionContext(sessionID, {})
  const runtime = new CoordinatorRuntime(async () => { throw new Error("legacy verifier forbidden") }, {
    repository: new RunRepository({ persistent: false }),
  })
  yield* Effect.addFinalizer(() => Effect.promise(async () => { await runtime.closeWorkspace(workspace); runtime.resetForTest() }))
  const base = builtinAutonomousDomainModules[0]!
  const host = new KernelHost(runtime, { directory: join(workspace, "plans"), autonomous: {
    modules: [{ ...base, prepare: (input) => input.intent.requirements.length === 1
      ? { status: "needs_input", reason: "information", questions: ["Which source revision?"] }
      : { status: "proceed", context: {} } }],
    artifactDirectory: join(workspace, "artifacts"), cleanupTimeoutMs: 1000, metering: { tokens: false, cost: false },
    limits: () => ({ deadlineAt: new Date(Date.now() + 60_000).toISOString(), maxActions: 10, maxParallelTasks: 1, maxTaskDepth: 0, maxTotalTasks: 1 }),
    authorize: async () => ({ capabilities: [{ operation: "read", targets: [{ kind: "workspace_path", selector: workspace }], exclusions: [] }],
      provenanceRefs: [{ sourceId: "fixture-policy", sha256: "a".repeat(64) }], expiresAt: new Date(Date.now() + 60_000).toISOString() }),
    ask: askAutonomousQuestions,
    adapter: async () => ({ resolveEffects: async () => [], invoke: async () => { throw new Error("no tool expected") },
      measure: async () => { throw new Error("no measurement expected") }, authenticates: () => false, cleanup: async () => [] }),
  } })
  const opened = yield* Effect.promise(() => host.openRun({ sessionID, workspace, goal: "Read the selected source revision", context,
    semantics: "autonomous-v1", defaultDomain: "general",
    domainExecutor: { id: "fixture", revision: "1", kind: "model_api", providerId: "local", modelId: "fixture", options: {} } }))
  const question = yield* Question.Service
  const events = yield* EventV2Bridge.Service
  const asked = yield* Queue.unbounded<void>()
  const off = yield* events.listen((event) => {
    if (event.type === Question.Event.Asked.type) Queue.offerUnsafe(asked, undefined)
    return Effect.void
  })
  yield* Effect.addFinalizer(() => off)
  const waiting = yield* Effect.tryPromise(() => host.requestAutonomousAnswers(sessionID, opened.runId)).pipe(Effect.forkScoped)
  let request: Question.Request | undefined
  while (!(request = (yield* question.list())[0])) yield* Queue.take(asked).pipe(Effect.timeout("5 seconds"))
  expect(request.sessionID).toBe(sessionID)
  expect(runtime.status(sessionID).autonomous!.lifecycle).toBe("waiting_input")
  if (mode === "answers") yield* question.reply({ requestID: request.id, answers: [["revision 7"]] })
  else if (mode === "dismiss") yield* question.reject(request.id)
  else yield* Effect.promise(() => runtime.cancel(sessionID))
  const result = yield* Fiber.await(waiting)
  expect(Exit.isSuccess(result)).toBe(mode === "answers")
  const status = runtime.status(sessionID).autonomous!
  expect(status.authority).toEqual(opened.autonomous.authority)
  expect(status.budget.actions).toBe(0)
  expect(status.intent.requirements).toHaveLength(mode === "answers" ? 2 : 1)
  expect(status.lifecycle).toBe(mode === "answers" ? "active" : mode === "dismiss" ? "waiting_input" : "closed")
  // Allow the aborted Effect's finalizer to remove the UI question before asserting.
  for (let attempt = 0; (yield* question.list()).length && attempt < 20; attempt++) yield* Effect.sleep("10 millis")
  expect(yield* question.list()).toEqual([])
}), 30000)
