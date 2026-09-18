import { expect } from "bun:test"
import { Effect, Exit } from "effect"
import { join } from "node:path"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { FSUtil } from "@base-harness/core/fs-util"
import { SessionProjector } from "@base-harness/core/session/projector"
import type { SubjectRef } from "@base-harness/domain-contracts"
import { Coordinator } from "../../src/harness/coordinator-service"
import { captureExecutionContext } from "../../src/harness/execution-context"
import { ToolRegistry } from "../../src/tool/registry"
import { Session } from "../../src/session/session"
import { Permission } from "../../src/permission"
import { Agent } from "../../src/agent/agent"
import { MessageID } from "../../src/session/schema"
import { TestInstance } from "../fixture/fixture"
import { testEffect } from "../lib/effect"

const it = testEffect(LayerNode.compile(LayerNode.group([ToolRegistry.node, FSUtil.node, Session.node, SessionProjector.node, Permission.node, Agent.node])))

it.instance("actual ToolRegistry, Sandbox and Python measure files, command failures and timeouts without mutating the workspace", () => Effect.gen(function* () {
  const fs = yield* FSUtil.Service
  const workspace = (yield* TestInstance).directory
  const source = join(workspace, "source.txt")
  yield* fs.writeFileString(source, "actual registry source\n")
  const session = yield* (yield* Session.Service).create({ title: "Autonomous tool test" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const context = yield* captureExecutionContext(session.id, { agent: "build", messageID: MessageID.ascending(), autonomousPolicy: { maxActions: 10, allowExecution: true } })
  const opened = yield* Effect.promise(() => Coordinator.openRun({ sessionID: session.id, workspace, context, goal: "Read the source",
    semantics: "autonomous-v1", defaultDomain: "general", domainExecutor: {
      id: "session-model", revision: "1", kind: "model_api", providerId: "fixture", modelId: "fixture", options: {},
    } }))
  expect(opened.autonomous.lifecycle).toBe("active")
  expect(() => Coordinator.assertToolAllowed(session.id, "read")).toThrow("ADMISSION_REQUIRED")
  const result = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "snapshot", {
    kind: "invoke", toolId: "read", arguments: { filePath: source, snapshot: true },
  }))
  if (!result.accepted) throw new Error(result.code)
  const data = result.output as unknown as { metadata: { subject: SubjectRef }; output: string }
  expect(data.output).toContain("actual registry source")
  const check = Coordinator.proposeAutonomousCheck(session.id, opened.runId, data.metadata.subject, { kind: "file", operator: "equals", expected: "different" })
  const measured = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "measure", {
    kind: "measure", subject: data.metadata.subject, checkRef: check.ref,
  }))
  if (!measured.accepted) throw new Error(measured.code)
  expect(measured.observation!.result).toMatchObject({ execution: "completed", findings: [{ name: "sha256" }, { name: "size" }, { result: "fail" }] })
  expect(Coordinator.status(session.id).autonomous!.lifecycle).toBe("active")
  const command = Coordinator.proposeAutonomousCheck(session.id, opened.runId, data.metadata.subject, {
    kind: "command", command: "printf 'command fact'; printf 'sandbox only' > source.txt; exit 1", expectedExitCode: 0,
  })
  const executed = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "command", {
    kind: "measure", subject: data.metadata.subject, checkRef: command.ref,
  }))
  if (!executed.accepted) throw new Error(executed.code)
  expect(executed.observation!.result).toMatchObject({ execution: "completed" })
  if (executed.observation!.result.execution === "completed") {
    expect(executed.observation!.result.findings).toContainEqual({ kind: "value", name: "stdout", observed: "command fact" })
    expect(executed.observation!.result.findings).toContainEqual({ kind: "comparison", name: "exit_code", operator: "equals", expected: 0, observed: 1, result: "fail" })
  }
  const timeoutCheck = Coordinator.proposeAutonomousCheck(session.id, opened.runId, data.metadata.subject, {
    kind: "command", command: "sleep 2; printf 'late' > source.txt", expectedExitCode: 0, timeoutMs: 100,
  })
  const timeoutStarted = Date.now()
  const timedOut = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "command-timeout", {
    kind: "measure", subject: data.metadata.subject, checkRef: timeoutCheck.ref,
  }))
  if (!timedOut.accepted) throw new Error(timedOut.code)
  expect(timedOut.observation!.result).toMatchObject({ execution: "error", error: { code: "TIMEOUT" } })
  expect(Date.now() - timeoutStarted).toBeLessThan(5000)
  const rejected = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "mutate", {
    kind: "invoke", toolId: "write", arguments: { filePath: source, content: "changed" },
  }))
  expect(rejected.accepted).toBe(false)
  expect(yield* fs.readFileString(source)).toBe("actual registry source\n")
  const finish = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "final", {
    kind: "final", text: "The source was read; the selected comparison failed.", openWork: "drain",
    assessment: { status: "partial", summary: "Observed comparison failure", uncertainties: ["Expected value may be incorrect"],
      citedObservationIds: [measured.observation!.observationId, executed.observation!.observationId, timedOut.observation!.observationId] },
  }))
  expect(finish.accepted).toBe(true)
  expect(Coordinator.status(session.id).autonomous!.completion?.assessment?.status).toBe("partial")
}), { git: true, config: { permission: { "*": "allow" } } }, 30000)

it.instance("denied app permission prevents autonomous authority before any tool admission", () => Effect.gen(function* () {
  const workspace = (yield* TestInstance).directory
  const session = yield* (yield* Session.Service).create({ title: "Autonomous permission denial" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const context = yield* captureExecutionContext(session.id, {
    agent: "build", messageID: MessageID.ascending(), autonomousPolicy: { maxActions: 4 },
  })
  const opened = yield* Effect.tryPromise(() => Coordinator.openRun({ sessionID: session.id, workspace, context, goal: "Read source.txt",
    semantics: "autonomous-v1", defaultDomain: "general", domainExecutor: {
      id: "session-model", revision: "1", kind: "model_api", providerId: "fixture", modelId: "fixture", options: {},
    } })).pipe(Effect.exit)
  expect(Exit.isFailure(opened)).toBe(true)
  expect(Coordinator.status(session.id).runId).toBe("")
}), { git: true, config: { permission: { read: "deny" } } }, 30000)
