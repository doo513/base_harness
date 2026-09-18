import { expect } from "bun:test"
import { Cause, Effect, Exit, Fiber } from "effect"
import { join } from "node:path"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { FSUtil } from "@base-harness/core/fs-util"
import { SessionProjector } from "@base-harness/core/session/projector"
import { ProviderV2 } from "@base-harness/core/provider"
import { ModelV2 } from "@base-harness/core/model"
import { Session } from "../../src/session/session"
import { SessionPrompt } from "../../src/session/prompt"
import { Question } from "../../src/question"
import { Coordinator } from "../../src/harness/coordinator-service"
import { TestInstance } from "../fixture/fixture"
import { testEffect } from "../lib/effect"
import { reply, httpError, TestLLMServer } from "../lib/llm-server"

const server = LayerNode.make({ service: TestLLMServer, layer: TestLLMServer.layer, deps: [] })
const it = testEffect(LayerNode.compile(LayerNode.group([SessionPrompt.node, Session.node, SessionProjector.node, FSUtil.node, Question.node, server])))

function find(value: unknown, predicate: (record: Record<string, any>) => boolean): Record<string, any> | undefined {
  if (typeof value === "string") { try { return find(JSON.parse(value), predicate) } catch { return } }
  if (!value || typeof value !== "object") return
  if (!Array.isArray(value) && predicate(value as Record<string, any>)) return value as Record<string, any>
  for (const child of Object.values(value)) { const found = find(child, predicate); if (found) return found }
}

it.instance("local model uses the existing loop for native read -> Python observation -> reinvestigation -> partial finish", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  const llm = yield* TestLLMServer
  yield* fs.writeFileString(join(workspace, "source.txt"), "actual model-loop source\n")
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1", autonomous: { maxActions: 20, timeoutMs: 120_000 } },
    provider: { fixture: { name: "Local fixture", id: "fixture", env: [], npm: "@ai-sdk/openai-compatible",
      options: { apiKey: "fixture-only", baseURL: llm.url }, models: { local: { id: "local", name: "Local fixture", attachment: false,
        reasoning: false, temperature: false, tool_call: true, release_date: "2025-01-01", limit: { context: 100000, output: 10000 },
        cost: { input: 0, output: 0 }, options: {} } } } },
  }))
  let step = 0
  yield* llm.respond(({ body }) => {
    const output = reply().usage({ input: 20, output: 5 })
    try {
    switch (step++) {
      case 0: {
        const serialized = JSON.stringify(body)
        if (!serialized.includes("workingGoal") || !serialized.includes("Read source.txt, check a comparison, and report the limitations.")) {
          throw new Error("Domain preparation context missing")
        }
        const toolNames = ((body.tools ?? []) as Array<{ function?: { name?: string } }>).map((item) => item.function?.name)
        if (["write", "edit", "apply_patch", "task", "skill", "bash"].some((name) => toolNames.includes(name))) {
          throw new Error("Unsupported autonomous tool was advertised")
        }
        return output.tool("read", { filePath: join(workspace, "source.txt"), snapshot: true })
      }
      case 1: {
        const source = find(body, (value) => value.subject?.kind === "source" && typeof value.preview === "string")
        if (!source) throw new Error("model did not receive source identity")
        return output.tool("harness_check", { subject: source.subject, parameters: { kind: "file", operator: "equals", expected: "incorrect expectation" } })
      }
      case 2: {
        const check = find(body, (value) => value.schemaVersion === "check-spec-v1")
        const source = find(body, (value) => value.subject?.kind === "source" && typeof value.preview === "string")
        if (!check || !source) throw new Error("model did not receive registered check")
        return output.tool("harness_decision", { kind: "measure", subject: source.subject, checkRef: check.ref })
      }
      case 3: {
        const observation = find(body, (value) => value.schemaVersion === "observation-v1")
        if (observation?.result.execution !== "completed" || !observation.result.findings.some((v: any) => v.result === "fail")) throw new Error("model did not receive the failed observation")
        return output.tool("read", { filePath: join(workspace, "source.txt"), snapshot: true })
      }
      case 4: {
        const observation = find(body, (value) => value.schemaVersion === "observation-v1")
        return output.text("The source was checked; the expectation remains uncertain.").tool("harness_decision", { kind: "final",
          text: "The source was checked; the expectation remains uncertain.", openWork: "drain",
          assessment: { status: "partial", summary: "Observed a mismatch", uncertainties: ["Test expectation"], citedObservationIds: [observation!.observationId] } })
      }
      default: throw new Error("unexpected automatic retry or additional model call")
    }
    } catch (error) { return httpError(400, { error: { message: error instanceof Error ? error.message : String(error) } }) }
  })
  const session = yield* (yield* Session.Service).create({ title: "Autonomous model integration" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const prompt = yield* SessionPrompt.Service
  const result = yield* prompt.prompt({ sessionID: session.id, agent: "build", model: { providerID: ProviderV2.ID.make("fixture"), modelID: ModelV2.ID.make("local") },
    parts: [{ type: "text", text: "Read source.txt, check a comparison, and report the limitations." }] })
  expect(result.info.role).toBe("assistant")
  const status = Coordinator.status(session.id)
  if (!status.autonomous?.completion) throw new Error(JSON.stringify({ phase: status.phase, lifecycle: status.autonomous?.lifecycle,
    calls: yield* llm.calls, step, error: result.info.role === "assistant" ? result.info.error : undefined,
    parts: result.parts.map((part) => part.type === "tool" ? { tool: part.tool, state: part.state } : { type: part.type }) }))
  expect(status.autonomous?.completion).toMatchObject({ reason: "requested", assessment: { status: "partial" } })
  expect(status.autonomous?.observations).toHaveLength(1)
  expect(status.autonomous?.budget.actions).toBe(8)
  expect(status.autonomous?.budget.used.modelTokens).toBe(125)
  expect(yield* llm.calls).toBe(5)
  expect(yield* fs.readFileString(join(workspace, "source.txt"))).toBe("actual model-loop source\n")
  expect(status.readyEligible).toBe(false)
}), { git: true }, 120000)

it.instance("plain model text is not_assessed even when it contains completion keywords", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  const llm = yield* TestLLMServer
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1" },
    provider: { fixture: { name: "Local fixture", id: "fixture", env: [], npm: "@ai-sdk/openai-compatible",
      options: { apiKey: "fixture-only", baseURL: llm.url }, models: { local: { id: "local", name: "Local fixture", attachment: false,
        reasoning: false, temperature: false, tool_call: true, release_date: "2025-01-01", limit: { context: 100000, output: 10000 },
        cost: { input: 0, output: 0 }, options: {} } } } },
  }))
  yield* llm.respond(() => reply().usage({ input: 3, output: 2 }).text("Ready, verified, and successful!").stop())
  const session = yield* (yield* Session.Service).create({ title: "Autonomous plain text" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    model: { providerID: ProviderV2.ID.make("fixture"), modelID: ModelV2.ID.make("local") },
    parts: [{ type: "text", text: "Give a short result." }] })
  expect(result.parts.find((part) => part.type === "text")?.text).toContain("Ready")
  expect(Coordinator.status(session.id).autonomous?.completion).toMatchObject({ reason: "requested", assessment: { status: "not_assessed" } })
  expect(Coordinator.status(session.id).readyEligible).toBe(false)
}), { git: true }, 120000)

it.instance("a model cannot replace the basis that was advertised with its tools", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  const llm = yield* TestLLMServer
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1" },
    provider: { fixture: { name: "Local fixture", id: "fixture", env: [], npm: "@ai-sdk/openai-compatible",
      options: { apiKey: "fixture-only", baseURL: llm.url }, models: { local: { id: "local", name: "Local fixture", attachment: false,
        reasoning: false, temperature: false, tool_call: true, release_date: "2025-01-01", limit: { context: 100000, output: 10000 },
        cost: { input: 0, output: 0 }, options: {} } } } },
  }))
  const forgedRef = { id: "forged", revision: 1, sha256: "f".repeat(64) }
  let step = 0
  yield* llm.respond(({ body }) => {
    if (step++ === 0) return reply().usage({ input: 2, output: 2 }).tool("harness_decision", { kind: "final", text: "Forged basis",
      basedOn: { runId: "forged", taskId: "forged", taskRevision: 1, intentRef: forgedRef, interpretationRef: forgedRef, authorityRef: forgedRef },
      openWork: "drain", assessment: { status: "satisfied", summary: "Forged", uncertainties: [], citedObservationIds: [] } })
    if (!JSON.stringify(body).includes("AUTONOMOUS_STALE_BASIS")) return httpError(400, { error: { message: "basis rejection missing" } })
    return reply().usage({ input: 2, output: 2 }).text("Basis stayed pinned.").tool("harness_decision", { kind: "final", text: "Basis stayed pinned.",
      openWork: "drain", assessment: { status: "partial", summary: "Pinned", uncertainties: [], citedObservationIds: [] } })
  })
  const session = yield* (yield* Session.Service).create({ title: "Autonomous basis pin" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    model: { providerID: ProviderV2.ID.make("fixture"), modelID: ModelV2.ID.make("local") },
    parts: [{ type: "text", text: "Finish without changing the advertised basis." }] })
  expect(Coordinator.status(session.id).autonomous?.completion).toMatchObject({ reason: "requested", assessment: { status: "partial" } })
  expect(yield* llm.calls).toBe(2)
}), { git: true }, 120000)

it.instance("unsupported token hard cap fails before the local provider is called", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  const llm = yield* TestLLMServer
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1", autonomous: { maxModelTokens: 100 } },
    provider: { fixture: { name: "Local fixture", id: "fixture", env: [], npm: "@ai-sdk/openai-compatible",
      options: { apiKey: "fixture-only", baseURL: llm.url }, models: { local: { id: "local", name: "Local fixture", attachment: false,
        reasoning: false, temperature: false, tool_call: true, release_date: "2025-01-01", limit: { context: 100000, output: 10000 },
        cost: { input: 0, output: 0 }, options: {} } } } },
  }))
  const session = yield* (yield* Session.Service).create({ title: "Unsupported hard cap" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    model: { providerID: ProviderV2.ID.make("fixture"), modelID: ModelV2.ID.make("local") },
    parts: [{ type: "text", text: "Do not call the provider." }] }).pipe(Effect.exit)
  expect(Exit.isFailure(result)).toBe(true)
  if (Exit.isFailure(result)) expect(Cause.pretty(result.cause)).toContain("BUDGET_CAPABILITY_UNSUPPORTED")
  expect(yield* llm.calls).toBe(0)
  expect(Coordinator.status(session.id).runId).toBe("")
}), { git: true }, 120000)

it.instance("model question pauses execution, uses the real Question service, then resumes the same Run", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  const llm = yield* TestLLMServer
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1", autonomous: { maxActions: 8, timeoutMs: 120_000 } },
    provider: { fixture: { name: "Local fixture", id: "fixture", env: [], npm: "@ai-sdk/openai-compatible",
      options: { apiKey: "fixture-only", baseURL: llm.url }, models: { local: { id: "local", name: "Local fixture", attachment: false,
        reasoning: false, temperature: false, tool_call: true, release_date: "2025-01-01", limit: { context: 100000, output: 10000 },
        cost: { input: 0, output: 0 }, options: {} } } } },
  }))
  let step = 0
  yield* llm.respond(({ body }) => {
    if (step++ === 0) return reply().usage({ input: 4, output: 2 }).tool("harness_decision", {
      kind: "ask", reason: "information", questions: ["Which revision should be reported?"],
    })
    if (!JSON.stringify(body).includes("revision 7")) return httpError(400, { error: { message: "authenticated answer missing" } })
    return reply().usage({ input: 4, output: 2 }).text("Reported revision 7.").tool("harness_decision", { kind: "final", text: "Reported revision 7.", openWork: "drain",
      assessment: { status: "partial", summary: "User selected revision 7", uncertainties: [], citedObservationIds: [] } })
  })
  const session = yield* (yield* Session.Service).create({ title: "Autonomous model question" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const pending = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    model: { providerID: ProviderV2.ID.make("fixture"), modelID: ModelV2.ID.make("local") },
    parts: [{ type: "text", text: "Ask which revision to report." }] }).pipe(Effect.forkScoped)
  const questions = yield* Question.Service
  let request: Question.Request | undefined
  for (let attempt = 0; !(request = (yield* questions.list())[0]) && attempt < 500; attempt++) yield* Effect.sleep("10 millis")
  if (!request) throw new Error("question was not presented")
  const waiting = Coordinator.status(session.id)
  expect(waiting.autonomous?.lifecycle).toBe("waiting_input")
  expect(waiting.autonomous?.budget.actions).toBe(1)
  yield* questions.reply({ requestID: request.id, answers: [["revision 7"]] })
  const result = yield* Fiber.join(pending)
  expect(result.parts.find((part) => part.type === "text")?.text).toContain("revision 7")
  expect(result.info.role).toBe("assistant")
  const status = Coordinator.status(session.id)
  expect(status.runId).toBe(waiting.runId)
  expect(status.autonomous?.intent.ref.revision).toBe(2)
  expect(status.autonomous?.completion).toMatchObject({ reason: "requested", assessment: { status: "partial" } })
  expect(yield* llm.calls).toBe(2)
}), { git: true }, 120000)

it.instance("cancelling an actual provider turn aborts it and records incomplete usage", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  const llm = yield* TestLLMServer
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1", autonomous: { timeoutMs: 120_000 } },
    provider: { fixture: { name: "Local fixture", id: "fixture", env: [], npm: "@ai-sdk/openai-compatible",
      options: { apiKey: "fixture-only", baseURL: llm.url }, models: { local: { id: "local", name: "Local fixture", attachment: false,
        reasoning: false, temperature: false, tool_call: true, release_date: "2025-01-01", limit: { context: 100000, output: 10000 },
        cost: { input: 0, output: 0 }, options: {} } } } },
  }))
  yield* llm.hang
  const session = yield* (yield* Session.Service).create({ title: "Autonomous model cancellation" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const running = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    model: { providerID: ProviderV2.ID.make("fixture"), modelID: ModelV2.ID.make("local") },
    parts: [{ type: "text", text: "Wait until cancelled." }] }).pipe(Effect.forkScoped)
  yield* llm.wait(1)
  const cancelled = yield* Effect.promise(() => Coordinator.cancel(session.id))
  expect(cancelled.autonomous?.completion).toMatchObject({ reason: "cancelled", assessment: null })
  expect(cancelled.autonomous?.budget.incompleteSettlementIds.some((id: string) => id.startsWith("model:"))).toBe(true)
  const promptExit = yield* Fiber.await(running)
  expect(Exit.isSuccess(promptExit)).toBe(true)
  if (Exit.isSuccess(promptExit)) expect(promptExit.value.info.role).toBe("assistant")
}), { git: true }, 120000)
