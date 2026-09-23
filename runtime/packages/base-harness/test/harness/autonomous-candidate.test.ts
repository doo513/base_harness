import { expect } from "bun:test"
import { Effect } from "effect"
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

const it = testEffect(LayerNode.compile(LayerNode.group([
  ToolRegistry.node, FSUtil.node, Session.node, SessionProjector.node, Permission.node, Agent.node,
])))

it.instance("stages a direct edit as a Candidate and publishes it only after explicit apply", () => Effect.gen(function* () {
  const fs = yield* FSUtil.Service
  const workspace = (yield* TestInstance).directory
  const target = join(workspace, "target.txt")
  yield* fs.writeFileString(target, "before\n")
  const session = yield* (yield* Session.Service).create({ title: "Autonomous Candidate" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const context = yield* captureExecutionContext(session.id, {
    agent: "build", messageID: MessageID.ascending(),
    autonomousPolicy: { maxActions: 12, allowMutation: true },
  })
  const opened = yield* Effect.promise(() => Coordinator.openRun({
    sessionID: session.id, workspace, context, goal: "Change target.txt", semantics: "autonomous-v1",
    defaultDomain: "develop", domainExecutor: {
      id: "session-model", revision: "1", kind: "model_api", providerId: "fixture", modelId: "fixture", options: {},
    },
  }))
  const staged = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "edit", {
    kind: "invoke", toolId: "edit", arguments: { filePath: target, oldString: "before\n", newString: "after\n" },
  }))
  if (!staged.accepted) throw new Error(staged.code)
  const output = staged.output as unknown as { candidate: SubjectRef & { kind: "candidate" }; candidateState: string }
  expect(output.candidateState).toBe("sealed")
  expect(yield* fs.readFileString(target)).toBe("before\n")
  expect(Coordinator.status(session.id).autonomous!.candidates).toMatchObject([
    { candidate: output.candidate, state: "sealed", files: [{ path: target }] },
  ])

  const check = Coordinator.proposeAutonomousCheck(session.id, opened.runId, output.candidate, {
    kind: "file", operator: "equals", expected: "after\n",
  })
  const measured = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "measure-candidate", {
    kind: "measure", subject: output.candidate, checkRef: check.ref,
  }))
  if (!measured.accepted) throw new Error(measured.code)
  expect(measured.observation!.result).toMatchObject({ execution: "completed", findings: [{ name: "sha256" }, { name: "size" }, { result: "pass" }] })

  const applied = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "apply", {
    kind: "apply_candidate", candidate: output.candidate,
  }))
  if (!applied.accepted) throw new Error(applied.code)
  expect(yield* fs.readFileString(target)).toBe("after\n")
  expect(Coordinator.status(session.id).autonomous!.candidates[0]!.state).toBe("applied")
}), { git: true, config: { permission: { "*": "allow" } } }, 30_000)

it.instance("rejects a conflicting apply and preserves the user's newer bytes", () => Effect.gen(function* () {
  const fs = yield* FSUtil.Service
  const workspace = (yield* TestInstance).directory
  const target = join(workspace, "target.txt")
  yield* fs.writeFileString(target, "baseline\n")
  const session = yield* (yield* Session.Service).create({ title: "Autonomous conflict" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const context = yield* captureExecutionContext(session.id, {
    agent: "build", messageID: MessageID.ascending(), autonomousPolicy: { maxActions: 8, allowMutation: true },
  })
  const opened = yield* Effect.promise(() => Coordinator.openRun({ sessionID: session.id, workspace, context,
    goal: "Change target.txt", semantics: "autonomous-v1", defaultDomain: "develop", domainExecutor: {
      id: "session-model", revision: "1", kind: "model_api", providerId: "fixture", modelId: "fixture", options: {},
    } }))
  const staged = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "write", {
    kind: "invoke", toolId: "write", arguments: { filePath: target, content: "candidate\n" },
  }))
  if (!staged.accepted) throw new Error(staged.code)
  const candidate = (staged.output as unknown as { candidate: SubjectRef & { kind: "candidate" } }).candidate
  yield* fs.writeFileString(target, "user-newer\n")
  const applied = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "apply", {
    kind: "apply_candidate", candidate,
  }))
  expect(applied).toMatchObject({ accepted: false, code: "WORKSPACE_CONFLICT" })
  expect(yield* fs.readFileString(target)).toBe("user-newer\n")
  expect(Coordinator.status(session.id).autonomous!.candidates[0]!.state).toBe("retained")
}), { git: true, config: { permission: { "*": "allow" } } }, 30_000)

it.instance("invalidates a sealed Candidate when edit permission is reduced before apply", () => Effect.gen(function* () {
  const fs = yield* FSUtil.Service
  const sessions = yield* Session.Service
  const workspace = (yield* TestInstance).directory
  const target = join(workspace, "target.txt")
  yield* fs.writeFileString(target, "baseline\n")
  const session = yield* sessions.create({ title: "Autonomous authority reduction" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const context = yield* captureExecutionContext(session.id, {
    agent: "build", messageID: MessageID.ascending(), autonomousPolicy: { maxActions: 10, allowMutation: true },
  })
  const opened = yield* Effect.promise(() => Coordinator.openRun({ sessionID: session.id, workspace, context,
    goal: "Change target.txt", semantics: "autonomous-v1", defaultDomain: "develop", domainExecutor: {
      id: "session-model", revision: "1", kind: "model_api", providerId: "fixture", modelId: "fixture", options: {},
    } }))
  const staged = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "write", {
    kind: "invoke", toolId: "write", arguments: { filePath: target, content: "candidate\n" },
  }))
  if (!staged.accepted) throw new Error(staged.code)
  const candidate = (staged.output as unknown as { candidate: SubjectRef & { kind: "candidate" } }).candidate

  yield* sessions.setPermission({ sessionID: session.id, permission: [
    { permission: "*", pattern: "*", action: "allow" },
    { permission: "edit", pattern: "*", action: "deny" },
  ] })
  const stale = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "apply-stale", {
    kind: "apply_candidate", candidate,
  }))
  expect(stale).toMatchObject({ accepted: false, code: "AUTONOMOUS_STALE_BASIS" })
  const forbidden = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "apply-current", {
    kind: "apply_candidate", candidate,
  }))
  expect(forbidden).toMatchObject({ accepted: false, code: "AUTONOMOUS_OPERATION_FORBIDDEN" })
  expect(yield* fs.readFileString(target)).toBe("baseline\n")
  expect(Coordinator.status(session.id).autonomous!.candidates[0]!.state).toBe("sealed")
}), { git: true, config: { permission: { "*": "allow" } } }, 30_000)

it.instance("captures a file-changing shell command in the same Candidate boundary", () => Effect.gen(function* () {
  if (process.platform === "win32") return
  const fs = yield* FSUtil.Service
  const workspace = (yield* TestInstance).directory
  const target = join(workspace, "shell.txt")
  yield* fs.writeFileString(target, "before")
  const session = yield* (yield* Session.Service).create({ title: "Autonomous shell Candidate" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const context = yield* captureExecutionContext(session.id, {
    agent: "build", messageID: MessageID.ascending(),
    autonomousPolicy: { maxActions: 10, allowExecution: true, allowMutation: true },
  })
  const opened = yield* Effect.promise(() => Coordinator.openRun({ sessionID: session.id, workspace, context,
    goal: "Change shell.txt using an isolated command", semantics: "autonomous-v1", defaultDomain: "develop", domainExecutor: {
      id: "session-model", revision: "1", kind: "model_api", providerId: "fixture", modelId: "fixture", options: {},
    } }))
  const staged = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "shell-write", {
    kind: "invoke", toolId: "bash", arguments: {
      command: "printf shell-after > shell.txt", workdir: workspace, mutation: "capture", timeout: 10_000,
    },
  }))
  if (!staged.accepted) throw new Error(staged.code)
  const candidate = (staged.output as unknown as { candidate: SubjectRef & { kind: "candidate" } }).candidate
  expect(yield* fs.readFileString(target)).toBe("before")
  const applied = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "shell-apply", {
    kind: "apply_candidate", candidate,
  }))
  if (!applied.accepted) throw new Error(applied.code)
  expect(yield* fs.readFileString(target)).toBe("shell-after")
}), { git: true, config: { permission: { "*": "allow" } } }, 30_000)

it.instance("applies update, move, and delete hunks only through Candidate publication", () => Effect.gen(function* () {
  const fs = yield* FSUtil.Service
  const workspace = (yield* TestInstance).directory
  const update = join(workspace, "update.txt")
  const move = join(workspace, "move.txt")
  const moved = join(workspace, "moved.txt")
  const remove = join(workspace, "remove.txt")
  yield* fs.writeFileString(update, "old\n")
  yield* fs.writeFileString(move, "move-old\n")
  yield* fs.writeFileString(remove, "delete-me\n")
  const session = yield* (yield* Session.Service).create({ title: "Autonomous patch Candidate" })
  yield* Effect.addFinalizer(() => Effect.promise(() => Coordinator.closeWorkspace(workspace)))
  const context = yield* captureExecutionContext(session.id, {
    agent: "build", messageID: MessageID.ascending(), autonomousPolicy: { maxActions: 10, allowMutation: true },
  })
  const opened = yield* Effect.promise(() => Coordinator.openRun({ sessionID: session.id, workspace, context,
    goal: "Patch workspace files", semantics: "autonomous-v1", defaultDomain: "develop", domainExecutor: {
      id: "session-model", revision: "1", kind: "model_api", providerId: "fixture", modelId: "fixture", options: {},
    } }))
  const patchText = `*** Begin Patch
*** Update File: update.txt
@@
-old
+new
*** Update File: move.txt
*** Move to: moved.txt
@@
-move-old
+move-new
*** Delete File: remove.txt
*** End Patch`
  const staged = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "patch", {
    kind: "invoke", toolId: "apply_patch", arguments: { patchText },
  }))
  if (!staged.accepted) throw new Error(staged.code)
  const candidate = (staged.output as unknown as { candidate: SubjectRef & { kind: "candidate" } }).candidate
  expect(yield* fs.readFileString(update)).toBe("old\n")
  expect(yield* fs.readFileString(move)).toBe("move-old\n")
  expect(yield* fs.readFileString(remove)).toBe("delete-me\n")
  expect(yield* fs.exists(moved)).toBe(false)
  const applied = yield* Effect.promise(() => Coordinator.submitAutonomousDecision(session.id, opened.runId, "patch-apply", {
    kind: "apply_candidate", candidate,
  }))
  if (!applied.accepted) throw new Error(applied.code)
  expect(yield* fs.readFileString(update)).toBe("new\n")
  expect(yield* fs.exists(move)).toBe(false)
  expect(yield* fs.readFileString(moved)).toBe("move-new\n")
  expect(yield* fs.exists(remove)).toBe(false)
}), { git: true, config: { permission: { "*": "allow" } } }, 30_000)
