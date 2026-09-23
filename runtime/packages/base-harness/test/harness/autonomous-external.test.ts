import { expect } from "bun:test"
import { Cause, Effect, Exit } from "effect"
import { join } from "node:path"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { FSUtil } from "@base-harness/core/fs-util"
import { SessionProjector } from "@base-harness/core/session/projector"
import { Session } from "../../src/session/session"
import { SessionPrompt } from "../../src/session/prompt"
import { Coordinator } from "../../src/harness/coordinator-service"
import type { ExecutionBackend } from "../../src/harness/execution/backend"
import { ExecutionBackends } from "../../src/harness/execution/backend-router"
import { TestInstance } from "../fixture/fixture"
import { testEffect } from "../lib/effect"

const it = testEffect(LayerNode.compile(LayerNode.group([SessionPrompt.node, Session.node, SessionProjector.node, FSUtil.node])))

const childProgram = String.raw`
const request = JSON.parse(await new Response(Bun.stdin.stream()).text())
const find = (value, predicate) => {
  if (typeof value === "string") { try { return find(JSON.parse(value), predicate) } catch { return } }
  if (!value || typeof value !== "object") return
  if (!Array.isArray(value) && predicate(value)) return value
  for (const child of Object.values(value)) { const result = find(child, predicate); if (result) return result }
}
let response
switch (STEP) {
  case 0:
    if (request.state.preparation?.context?.workingGoal !== "Read source.txt, measure it, and report what is known.") throw new Error("Domain preparation context missing")
    response = { schemaVersion: "autonomous-backend-response-v1", kind: "decision",
      response: { kind: "invoke", toolId: "read", arguments: { filePath: request.state.intent.requirements[0].text.match(/\S+\.txt/)[0], snapshot: true } } }
    break
  case 1: {
    const source = find(request.previous, (value) => value.subject?.kind === "source" && typeof value.preview === "string")
    if (!source) throw new Error("source result missing")
    response = { schemaVersion: "autonomous-backend-response-v1", kind: "register_check", subject: source.subject,
      parameters: { kind: "file", operator: "equals", expected: "wrong expectation" } }
    break
  }
  case 2: {
    const check = find(request.previous, (value) => value.schemaVersion === "check-spec-v1")
    if (!check) throw new Error("check result missing")
    const source = find(request.history, (value) => value.kind === "source" && typeof value.sha256 === "string")
    if (!source) throw new Error("source history missing")
    response = { schemaVersion: "autonomous-backend-response-v1", kind: "decision",
      response: { kind: "measure", subject: source, checkRef: check.ref } }
    break
  }
  case 3: {
    const observation = request.state.observations[0]
    if (observation?.result.execution !== "completed" || !observation.result.findings.some((item) => item.result === "fail")) throw new Error("failed observation missing")
    response = { schemaVersion: "autonomous-backend-response-v1", kind: "decision", response: { kind: "final",
      text: "The controlled external process observed a mismatch.", openWork: "drain",
      assessment: { status: "partial", summary: "Observed mismatch", uncertainties: ["Expected value"], citedObservationIds: [observation.observationId] } } }
    break
  }
  default: throw new Error("unexpected external turn")
}
process.stdout.write(JSON.stringify(response))
`

it.instance("controlled external process uses the pinned autonomous decision protocol and Python observation path", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  yield* fs.writeFileString(join(workspace, "source.txt"), "external source\n")
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" },
    kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1", autonomous: { maxActions: 16, timeoutMs: 120_000 } },
  }))
  let step = 0
  const calls: Array<{ runId?: string; phase?: string }> = []
  const backend: ExecutionBackend = {
    id: "autonomous-controlled-process", kind: "agent_runtime",
    async discover() { return { adapterID: this.id, backendId: this.id, kind: this.kind, revision: "fixture-r1",
      models: ["fixture-model"], reasoningEfforts: [],
      autonomousDecision: { protocol: "autonomous-decision-v1", resourceUsage: "reported-v1" } } },
    async execute(input) {
      if (!Object.isFrozen(input.selection) || !Object.isFrozen(input.selection.nativeOptions)) throw new Error("selection was not pinned")
      calls.push({ runId: input.runId, phase: input.phase })
      const program = childProgram.replace("STEP", String(step++))
      const child = Bun.spawn([process.execPath, "-e", program], { cwd: input.workspace, stdin: "pipe", stdout: "pipe", stderr: "pipe" })
      await child.stdin.write(input.prompt)
      await child.stdin.end()
      const [output, error, code] = await Promise.all([
        new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited,
      ])
      if (code !== 0) throw new Error(error)
      return { output, changedFiles: [], capabilityRevision: "fixture-r1", backendId: this.id,
        modelId: input.selection.modelId, nativeOptions: input.selection.nativeOptions,
        resourceUsage: { modelTokens: 7, costMinorUnits: 0 } }
    },
  }
  ExecutionBackends.register(backend)
  expect(Object.isFrozen(ExecutionBackends.get(backend.id))).toBe(true)
  expect(() => ExecutionBackends.register({ ...backend })).toThrow("BACKEND_ALREADY_REGISTERED")
  const session = yield* (yield* Session.Service).create({ title: "Autonomous external integration" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  yield* Effect.promise(() => Coordinator.control(session.id, { type: "execution.select", selection: {
    adapterID: backend.id, modelID: "fixture-model", capabilityRevision: "fixture-r1", kind: "agent_runtime",
  } }, undefined, workspace))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    parts: [{ type: "text", text: "Read source.txt, measure it, and report what is known." }] })
  expect(result.parts.find((part) => part.type === "text")?.text).toBe("The controlled external process observed a mismatch.")
  const status = Coordinator.status(session.id)
  expect(status.autonomous?.completion).toMatchObject({ reason: "requested", assessment: { status: "partial" } })
  expect(status.autonomous?.observations).toHaveLength(1)
  expect(status.autonomous?.budget.actions).toBe(6)
  expect(status.autonomous?.budget.used.modelTokens).toBe(28)
  expect(calls).toHaveLength(4)
  expect(new Set(calls.map((call) => call.runId))).toEqual(new Set([status.runId]))
  expect(calls.every((call) => call.phase === "autonomous_decision")).toBe(true)
  expect(yield* fs.readFileString(join(workspace, "source.txt"))).toBe("external source\n")
  expect(status.readyEligible).toBe(false)
}), { git: true }, 120000)

it.instance("controlled external decisions stage and explicitly apply a Develop Candidate", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  const target = join(workspace, "external-change.txt")
  yield* fs.writeFileString(target, "before\n")
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" },
    kernel: { defaultDomain: "develop", autonomous: { maxActions: 12, timeoutMs: 120_000 } },
  }))
  let step = 0
  const backend: ExecutionBackend = {
    id: "autonomous-controlled-mutation", kind: "agent_runtime",
    async discover() { return { adapterID: this.id, backendId: this.id, kind: this.kind, revision: "mutation-r1",
      models: ["fixture-model"], reasoningEfforts: [],
      autonomousDecision: { protocol: "autonomous-decision-v1", resourceUsage: "reported-v1" } } },
    async execute(input) {
      const request = JSON.parse(input.prompt)
      let response: unknown
      if (step++ === 0) {
        response = { kind: "invoke", toolId: "write", arguments: { filePath: target, content: "after\n" } }
      } else if (step === 2) {
        const candidate = request.state.candidates[0]?.candidate
        if (!candidate || request.state.candidates[0]?.state !== "sealed") throw new Error("sealed Candidate missing")
        response = { kind: "apply_candidate", candidate }
      } else if (step === 3) {
        if (request.state.candidates[0]?.state !== "applied") throw new Error("applied Candidate missing")
        response = { kind: "final", text: "External Candidate applied.", openWork: "drain",
          assessment: { status: "satisfied", summary: "Candidate applied", uncertainties: [], citedObservationIds: [] } }
      } else throw new Error("unexpected external mutation turn")
      return { output: JSON.stringify({ schemaVersion: "autonomous-backend-response-v1", kind: "decision", response }),
        changedFiles: [], capabilityRevision: "mutation-r1", backendId: this.id, modelId: input.selection.modelId,
        nativeOptions: input.selection.nativeOptions, resourceUsage: { modelTokens: 5, costMinorUnits: 0 } }
    },
  }
  ExecutionBackends.register(backend)
  const session = yield* (yield* Session.Service).create({ title: "Autonomous external mutation" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  yield* Effect.promise(() => Coordinator.control(session.id, { type: "execution.select", selection: {
    adapterID: backend.id, modelID: "fixture-model", capabilityRevision: "mutation-r1", kind: "agent_runtime",
  } }, undefined, workspace))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    parts: [{ type: "text", text: "Change external-change.txt and explicitly apply the Candidate." }] })
  expect(result.parts.find((part) => part.type === "text")?.text).toBe("External Candidate applied.")
  expect(yield* fs.readFileString(target)).toBe("after\n")
  expect(Coordinator.status(session.id).autonomous?.candidates[0]).toMatchObject({ state: "applied" })
  expect(Coordinator.status(session.id).autonomous?.completion).toMatchObject({
    reason: "requested", assessment: { status: "satisfied" },
  })
  expect(Coordinator.status(session.id).autonomousResult).toMatchObject({
    schemaVersion: "autonomous-product-result-v1",
    lifecycle: "closed",
    runtimeReason: "requested",
    assessment: { status: "satisfied" },
    candidates: [{ state: "applied" }],
  })
}), { git: true }, 120000)

it.instance("plain external output closes as not_assessed without inferring success words", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1" },
  }))
  const backend: ExecutionBackend = {
    id: "autonomous-plain-output", kind: "agent_runtime",
    async discover() { return { adapterID: this.id, backendId: this.id, kind: this.kind, revision: "plain-r1",
      models: ["fixture-model"], reasoningEfforts: [],
      autonomousDecision: { protocol: "autonomous-decision-v1", resourceUsage: "reported-v1" } } },
    async execute(input) { return { output: "Ready, verified, and successful!", changedFiles: [], capabilityRevision: "plain-r1",
      backendId: this.id, modelId: input.selection.modelId, nativeOptions: input.selection.nativeOptions,
      resourceUsage: { modelTokens: 4, costMinorUnits: 0 } } },
  }
  ExecutionBackends.register(backend)
  const session = yield* (yield* Session.Service).create({ title: "Plain external output" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  yield* Effect.promise(() => Coordinator.control(session.id, { type: "execution.select", selection: {
    adapterID: backend.id, modelID: "fixture-model", capabilityRevision: "plain-r1", kind: "agent_runtime",
  } }, undefined, workspace))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    parts: [{ type: "text", text: "Report the result." }] })
  expect(result.parts.find((part) => part.type === "text")?.text).toBe("Ready, verified, and successful!")
  expect(Coordinator.status(session.id).autonomous?.completion).toMatchObject({
    reason: "requested", assessment: { status: "not_assessed" },
  })
  expect(Coordinator.status(session.id).readyEligible).toBe(false)
}), { git: true }, 120000)

it.instance("malformed structured final preserves only report text as not_assessed", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1" },
  }))
  const backend: ExecutionBackend = {
    id: "autonomous-malformed-final", kind: "agent_runtime",
    async discover() { return { adapterID: this.id, backendId: this.id, kind: this.kind, revision: "malformed-r1",
      models: ["fixture-model"], reasoningEfforts: [],
      autonomousDecision: { protocol: "autonomous-decision-v1", resourceUsage: "reported-v1" } } },
    async execute(input) { return { output: JSON.stringify({
      schemaVersion: "autonomous-backend-response-v1", kind: "decision",
      response: { kind: "final", text: "Useful prose", assessment: "success", openWork: "later" },
    }), changedFiles: [], capabilityRevision: "malformed-r1",
      backendId: this.id, modelId: input.selection.modelId, nativeOptions: input.selection.nativeOptions,
      resourceUsage: { modelTokens: 4, costMinorUnits: 0 } } },
  }
  ExecutionBackends.register(backend)
  const session = yield* (yield* Session.Service).create({ title: "Malformed external final" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  yield* Effect.promise(() => Coordinator.control(session.id, { type: "execution.select", selection: {
    adapterID: backend.id, modelID: "fixture-model", capabilityRevision: "malformed-r1", kind: "agent_runtime",
  } }, undefined, workspace))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    parts: [{ type: "text", text: "Return prose." }] })
  expect(result.parts.find((part) => part.type === "text")?.text).toBe("Useful prose")
  expect(Coordinator.status(session.id).autonomous?.completion).toMatchObject({
    reason: "requested", assessment: { status: "not_assessed", summary: "Useful prose" },
  })
}), { git: true }, 120000)

it.instance("an external response cannot replace the basis captured before execution", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1" },
  }))
  const forgedRef = { id: "forged", revision: 1, sha256: "f".repeat(64) }
  let calls = 0
  const backend: ExecutionBackend = {
    id: "autonomous-forged-basis", kind: "agent_runtime",
    async discover() { return { adapterID: this.id, backendId: this.id, kind: this.kind, revision: "basis-r1",
      models: ["fixture-model"], reasoningEfforts: [],
      autonomousDecision: { protocol: "autonomous-decision-v1", resourceUsage: "reported-v1" } } },
    async execute(input) {
      const priorRejected = input.prompt.includes("AUTONOMOUS_STALE_BASIS")
      const response = calls++ === 0
        ? { kind: "final", text: "Forged", basedOn: { runId: "forged", taskId: "forged", taskRevision: 1,
            intentRef: forgedRef, interpretationRef: forgedRef, authorityRef: forgedRef }, openWork: "drain",
            assessment: { status: "satisfied", summary: "Forged", uncertainties: [], citedObservationIds: [] } }
        : { kind: "final", text: priorRejected ? "Basis stayed pinned." : "Missing rejection", openWork: "drain",
            assessment: { status: "partial", summary: "Pinned", uncertainties: [], citedObservationIds: [] } }
      return { output: JSON.stringify({ schemaVersion: "autonomous-backend-response-v1", kind: "decision", response }),
        changedFiles: [], capabilityRevision: "basis-r1", backendId: this.id, modelId: input.selection.modelId,
        nativeOptions: input.selection.nativeOptions, resourceUsage: { modelTokens: 2, costMinorUnits: 0 } }
    },
  }
  ExecutionBackends.register(backend)
  const session = yield* (yield* Session.Service).create({ title: "External basis pin" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  yield* Effect.promise(() => Coordinator.control(session.id, { type: "execution.select", selection: {
    adapterID: backend.id, modelID: "fixture-model", capabilityRevision: "basis-r1", kind: "agent_runtime",
  } }, undefined, workspace))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    parts: [{ type: "text", text: "Finish using only the advertised basis." }] })
  expect(result.parts.find((part) => part.type === "text")?.text).toBe("Basis stayed pinned.")
  expect(Coordinator.status(session.id).autonomous?.completion).toMatchObject({ reason: "requested", assessment: { status: "partial" } })
  expect(calls).toBe(2)
}), { git: true }, 120000)

it.instance("an external backend without the explicit decision capability fails without legacy fallback", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const fs = yield* FSUtil.Service
  yield* fs.writeFileString(join(workspace, "base-harness.jsonc"), JSON.stringify({
    permission: { "*": "allow" }, kernel: { defaultDomain: "general", executionSemantics: "autonomous-v1" },
  }))
  let executed = 0
  const backend: ExecutionBackend = {
    id: "autonomous-unsupported", kind: "agent_runtime",
    async discover() { return { adapterID: this.id, backendId: this.id, kind: this.kind, revision: "unsupported-r1",
      models: ["fixture-model"], reasoningEfforts: [] } },
    async execute(input) { executed++; return { output: "legacy prose", changedFiles: [], capabilityRevision: "unsupported-r1",
      backendId: this.id, modelId: input.selection.modelId, nativeOptions: input.selection.nativeOptions } },
  }
  ExecutionBackends.register(backend)
  const session = yield* (yield* Session.Service).create({ title: "Unsupported external protocol" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  yield* Effect.promise(() => Coordinator.control(session.id, { type: "execution.select", selection: {
    adapterID: backend.id, modelID: "fixture-model", capabilityRevision: "unsupported-r1", kind: "agent_runtime",
  } }, undefined, workspace))
  const result = yield* (yield* SessionPrompt.Service).prompt({ sessionID: session.id, agent: "build",
    parts: [{ type: "text", text: "Report the result." }] }).pipe(Effect.exit)
  expect(Exit.isFailure(result)).toBe(true)
  if (Exit.isFailure(result)) expect(Cause.pretty(result.cause)).toContain("does not support autonomous-decision-v1")
  expect(executed).toBe(0)
  expect(Coordinator.status(session.id).autonomous?.lifecycle).toBe("active")
}), { git: true }, 120000)
