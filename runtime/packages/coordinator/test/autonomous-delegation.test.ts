import { expect, test } from "bun:test"
import { mkdtemp, rm } from "node:fs/promises"
import { join } from "node:path"
import { tmpdir } from "node:os"
import type {
  AutonomousRunSetup, AutonomousRunPorts, DecisionProposal, TaskProposal,
  AutonomousCandidateSeal, SubjectRef, VersionRef, AutonomousDecisionResult,
  AutonomousTaskExecutionInput, AutonomousTaskExecutionResult, DecisionAction,
} from "@base-harness/domain-contracts"
import { AutonomousRun } from "../src/autonomous-run"
import { CoordinatorRuntime, RunRepository } from "../src"

const ref = (id: string, revision = 1) => ({ id, revision, sha256: "a".repeat(64) })
const rejectionCode = (result: AutonomousDecisionResult) => {
  if (result.accepted) throw new Error("Expected an autonomous admission rejection")
  return result.code
}

function createSetup(runId: string, root: string, taskId = "root-task", overrides?: Partial<AutonomousRunSetup["limits"]>): AutonomousRunSetup {
  return {
    binding: {
      schemaVersion: "autonomous-run-binding-v1",
      semantics: "autonomous-v1",
      runId,
      domainModule: ref("general"),
      executor: ref("fixture"),
      authorityRef: ref("grant"),
      budgetId: `${runId}:budget`,
    },
    taskId,
    intent: {
      schemaVersion: "intent-v1",
      ref: ref("intent"),
      originalRequest: { ...ref("source"), kind: "source" },
      requirements: [],
      constraints: [],
    },
    interpretation: {
      schemaVersion: "interpretation-v1",
      ref: ref("interpretation"),
      intentRef: ref("intent"),
      goalSummary: "Delegation test hypothesis",
      assumptions: [],
      openQuestions: [],
      proposedCheckIds: [],
    },
    authority: {
      schemaVersion: "authority-v1",
      ref: ref("grant"),
      runId,
      provenanceRefs: [{ sourceId: "user", sha256: "b".repeat(64) }],
      expiresAt: new Date(Date.now() + 120_000).toISOString(),
      capabilities: [
        { operation: "read", targets: [{ kind: "workspace_path", selector: root }], exclusions: [] },
        { operation: "mutate", targets: [{ kind: "workspace_path", selector: root }], exclusions: [] },
        { operation: "delegate", targets: [{ kind: "workspace_path", selector: root }], exclusions: [] },
      ],
    },
    limits: {
      deadlineAt: new Date(Date.now() + 120_000).toISOString(),
      maxActions: 50,
      maxParallelTasks: 2,
      maxTaskDepth: 2,
      maxTotalTasks: 10,
      ...overrides,
    },
    metering: { tokens: false, cost: false },
    cleanupTimeoutMs: 1000,
    checks: [],
    gates: [],
    subjects: [{ ...ref("report"), kind: "report" }],
    gateEvidence: {},
  }
}

function createDefaultPorts(root: string, overrides?: Partial<AutonomousRunPorts>): AutonomousRunPorts {
  return {
    resolveEffects: async (action) => {
      if (action.kind === "invoke") {
        return [{ operation: "read", targets: [{ kind: "workspace_path", selector: join(root, "file").replaceAll("\\", "/") }] }]
      }
      if (action.kind === "apply_candidate") {
        return [{ operation: "mutate", targets: [{ kind: "workspace_path", selector: root }] }]
      }
      return []
    },
    invoke: async () => "mock-invoke-result",
    measure: async () => { throw new Error("no checks") },
    authenticates: () => true,
    revise: ({ basedOnRef, ...value }) => ({ ...value, ref: { ...ref(basedOnRef.id), revision: basedOnRef.revision + 1 } }),
    cleanup: async () => [],
    executeTask: async (task: AutonomousTaskExecutionInput): Promise<AutonomousTaskExecutionResult> => {
      return { output: `completed:${task.taskId}` }
    },
    ...overrides,
  }
}

test("M4-B: Hierarchical governance - capability escalation is rejected", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-gov-cap-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-cap", root)
    setup.authority.capabilities = [
      { operation: "read", targets: [{ kind: "workspace_path", selector: root }], exclusions: [] },
      { operation: "delegate", targets: [{ kind: "workspace_path", selector: root }], exclusions: [] },
    ]
    const ports = createDefaultPorts(root)
    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    const proposal: DecisionProposal = {
      schemaVersion: "decision-v1",
      decisionId: "dec-escalate-cap",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "sub-1",
            objective: "Attempt unauthorized mutation",
            requestedCapabilities: ["read", "mutate"],
            requestedScopes: [{ kind: "workspace_path", selector: root }],
            dependsOn: [],
          },
        ],
      },
    }

    const result = await run.submit(proposal)
    expect(result.accepted).toBe(false)
    expect(rejectionCode(result)).toBe("AUTONOMOUS_TASK_CAPABILITY_ESCALATION")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: Hierarchical governance - scope escalation is rejected", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-gov-scope-"))).replaceAll("\\", "/")
  const subDir = join(root, "sub").replaceAll("\\", "/")
  try {
    const setup = createSetup("run-scope", root)
    setup.authority.capabilities = [
      { operation: "read", targets: [{ kind: "workspace_path", selector: subDir }], exclusions: [] },
      { operation: "delegate", targets: [{ kind: "workspace_path", selector: subDir }], exclusions: [] },
    ]
    const ports = createDefaultPorts(root)
    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    const proposal: DecisionProposal = {
      schemaVersion: "decision-v1",
      decisionId: "dec-escalate-scope",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "sub-scope",
            objective: "Attempt broader workspace scope",
            requestedCapabilities: ["read"],
            requestedScopes: [{ kind: "workspace_path", selector: root }],
            dependsOn: [],
          },
        ],
      },
    }

    const result = await run.submit(proposal)
    expect(result.accepted).toBe(false)
    expect(["AUTONOMOUS_OPERATION_FORBIDDEN", "AUTONOMOUS_TASK_SCOPE_ESCALATION"]).toContain(rejectionCode(result))
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: Hierarchical governance - depth limit is strictly enforced", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-gov-depth-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-depth", root, "root-task", { maxTaskDepth: 1 })
    let childTaskId = ""

    const ports = createDefaultPorts(root, {
      executeTask: async (task) => {
        childTaskId = task.taskId
        return { output: "child-done" }
      },
    })
    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    const delegateResult = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-del-1",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "child-1",
            objective: "Child task at depth 1",
            requestedCapabilities: ["read", "delegate"],
            requestedScopes: [{ kind: "workspace_path", selector: root }],
            dependsOn: [],
          },
        ],
      },
    })
    expect(delegateResult.accepted).toBe(true)
    expect(childTaskId).toBeTruthy()

    const snapshot = run.snapshot()
    const childTask = snapshot.tasks.find((t) => t.taskId === childTaskId)!
    expect(childTask.depth).toBe(1)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: Hierarchical governance - depth limit check while child is active", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-gov-depth-active-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-depth-active", root, "root-task", { maxTaskDepth: 1 })
    let unblockChild: () => void = () => {}
    let childTaskId = ""

    const ports = createDefaultPorts(root, {
      executeTask: async (task) => {
        childTaskId = task.taskId
        await new Promise<void>((resolve) => { unblockChild = resolve })
        return { output: "child-done" }
      },
    })
    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    const del = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-root-del",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "child-active",
            objective: "Active child at depth 1",
            requestedCapabilities: ["read", "delegate"],
            requestedScopes: [{ kind: "workspace_path", selector: root }],
            dependsOn: [],
          },
        ],
      },
    })

    await new Promise((r) => setTimeout(r, 20))
    expect(childTaskId).toBeTruthy()

    // Child task is currently running at depth 1. It attempts to delegate grandchild
    const grandchildProposal: DecisionProposal = {
      schemaVersion: "decision-v1",
      decisionId: "dec-grandchild-active",
      basis: run.basis(childTaskId),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "grandchild-1",
            objective: "Grandchild at depth 2",
            requestedCapabilities: ["read"],
            requestedScopes: [{ kind: "workspace_path", selector: root }],
            dependsOn: [],
          },
        ],
      },
    }

    const grandchildResult = await run.submit(grandchildProposal)
    expect(grandchildResult.accepted).toBe(false)
    expect(rejectionCode(grandchildResult)).toBe("AUTONOMOUS_TASK_DEPTH_EXCEEDED")

    unblockChild()
    await del
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: Hierarchical governance - key conflict, total limit, and invalid dependencies", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-gov-limits-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-limits", root, "root-task", { maxTotalTasks: 3 })
    const ports = createDefaultPorts(root, {
      executeTask: async () => new Promise<never>(() => undefined),
    })
    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    // 1. Duplicate clientTaskKey in same proposal
    const dupResult = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-dup",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          { clientTaskKey: "key-a", objective: "Task A", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "key-a", objective: "Task A duplicate", requestedCapabilities: ["read"], dependsOn: [] },
        ],
      },
    })
    expect(dupResult.accepted).toBe(false)
    expect(rejectionCode(dupResult)).toBe("AUTONOMOUS_TASK_KEY_CONFLICT")

    // 2. Invalid dependency
    const badDepResult = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-bad-dep",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "key-valid",
            objective: "Task with phantom dependency",
            requestedCapabilities: ["read"],
            dependsOn: [{ taskId: "phantom-task-id", when: "settled" }],
          },
        ],
      },
    })
    expect(badDepResult.accepted).toBe(false)
    expect(rejectionCode(badDepResult)).toBe("AUTONOMOUS_TASK_DEPENDENCY_INVALID")

    // 3. Exceeding maxTotalTasks limit
    const exceedLimitResult = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-exceed",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          { clientTaskKey: "t1", objective: "Task 1", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "t2", objective: "Task 2", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "t3", objective: "Task 3", requestedCapabilities: ["read"], dependsOn: [] },
        ],
      },
    })
    expect(exceedLimitResult.accepted).toBe(false)
    expect(rejectionCode(exceedLimitResult)).toBe("AUTONOMOUS_TASK_LIMIT_EXCEEDED")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: Concurrency control - maxParallelTasks throttling and auto-dispatch", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-concurrency-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-parallel", root, "root-task", { maxParallelTasks: 2, maxTotalTasks: 10 })
    const resolvers = new Map<string, () => void>()
    const activeTasks = new Set<string>()
    let maxObservedActive = 0

    const ports = createDefaultPorts(root, {
      executeTask: async (task) => {
        activeTasks.add(task.taskId)
        maxObservedActive = Math.max(maxObservedActive, activeTasks.size)
        await new Promise<void>((resolve) => {
          resolvers.set(task.taskId, () => {
            activeTasks.delete(task.taskId)
            resolve()
          })
        })
        return { output: `done:${task.taskId}` }
      },
    })
    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    const delegatePromise = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-4-tasks",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          { clientTaskKey: "p1", objective: "P1", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "p2", objective: "P2", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "p3", objective: "P3", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "p4", objective: "P4", requestedCapabilities: ["read"], dependsOn: [] },
        ],
      },
    })

    await new Promise((r) => setTimeout(r, 20))

    // Exactly 2 subtasks should be running concurrently
    expect(activeTasks.size).toBe(2)
    expect(maxObservedActive).toBe(2)

    let snap = run.snapshot()
    const runningBefore = snap.tasks.filter((t) => t.taskId !== "root-task" && t.state === "running")
    const pendingBefore = snap.tasks.filter((t) => t.taskId !== "root-task" && t.state === "pending")
    expect(runningBefore.length).toBe(2)
    expect(pendingBefore.length).toBe(2)

    // Complete one running subtask
    const firstRunning = runningBefore[0]!
    resolvers.get(firstRunning.taskId)! ()
    await new Promise((r) => setTimeout(r, 20))

    // Next pending subtask should be dispatched
    expect(activeTasks.size).toBe(2)
    expect(maxObservedActive).toBe(2)
    snap = run.snapshot()
    expect(snap.tasks.filter((t) => t.taskId !== "root-task" && t.state === "running").length).toBe(2)
    expect(snap.tasks.filter((t) => t.taskId !== "root-task" && t.state === "pending").length).toBe(1)
    expect(snap.tasks.filter((t) => t.taskId !== "root-task" && t.state === "settled").length).toBe(1)

    // Complete all remaining subtasks iteratively as slots open
    snap = run.snapshot()
    while (snap.tasks.filter((t) => t.taskId !== "root-task" && t.state === "settled").length < 4) {
      for (const res of [...resolvers.values()]) res()
      await new Promise((r) => setTimeout(r, 15))
      snap = run.snapshot()
    }
    await delegatePromise

    expect(snap.tasks.filter((t) => t.taskId !== "root-task" && t.state === "settled").length).toBe(4)
    expect(activeTasks.size).toBe(0)
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: DAG dependency - when 'settled' gates execution", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-dag-settled-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-dag-settled", root, "root-task", { maxParallelTasks: 4 })
    let unblockA: () => void = () => {}
    let taskAId = ""
    let taskBStarted = false

    const ports = createDefaultPorts(root, {
      executeTask: async (task) => {
        if (task.proposal.clientTaskKey === "task-a") {
          taskAId = task.taskId
          await new Promise<void>((resolve) => { unblockA = resolve })
          return { output: "a-done" }
        }
        if (task.proposal.clientTaskKey === "task-b") {
          taskBStarted = true
          return { output: "b-done" }
        }
        return { output: "other" }
      },
    })
    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    // Delegate task A (in flight)
    const delA = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-a",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [{ clientTaskKey: "task-a", objective: "Task A", requestedCapabilities: ["read"], dependsOn: [] }],
      },
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(taskAId).toBeTruthy()

    // While Task A is running, delegate Task B depending on Task A when: "settled"
    const delB = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-b",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "task-b",
            objective: "Task B waiting on A",
            requestedCapabilities: ["read"],
            dependsOn: [{ taskId: taskAId, when: "settled" }],
          },
        ],
      },
    })
    await new Promise((r) => setTimeout(r, 20))

    // Task B must NOT have started because Task A is still running
    expect(taskBStarted).toBe(false)
    let snap = run.snapshot()
    const taskB = snap.tasks.find((t) => t.clientTaskKey === "task-b")!
    expect(taskB.state).toBe("pending")

    // Now unblock Task A to settle
    unblockA()
    await delA
    await delB
    await new Promise((r) => setTimeout(r, 30))

    // Task B must now have been dispatched and settled!
    expect(taskBStarted).toBe(true)
    snap = run.snapshot()
    expect(snap.tasks.find((t) => t.clientTaskKey === "task-b")?.state).toBe("settled")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: DAG dependency - when 'artifact_produced' unblocks before task settlement", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-dag-artifact-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-dag-art", root, "root-task", { maxParallelTasks: 4 })
    let taskAId = ""
    let taskCStarted = false
    let unblockA: () => void = () => {}

    const candSubject: SubjectRef & { kind: "candidate" } = {
      id: "candidate-seal-1",
      revision: 1,
      sha256: "c".repeat(64),
      kind: "candidate",
    }
    setup.subjects.push(candSubject)

    const ports = createDefaultPorts(root, {
      resolveEffects: async (action) => {
        if (action.kind === "invoke") return [{ operation: "mutate", targets: [{ kind: "workspace_path", selector: root }] }]
        return []
      },
      beginMutation: async () => {},
      executeTask: async (task) => {
        if (task.proposal.clientTaskKey === "producer-a") {
          taskAId = task.taskId
          await new Promise<void>((resolve) => { unblockA = resolve })
          return { output: "producer-done" }
        }
        if (task.proposal.clientTaskKey === "consumer-c") {
          taskCStarted = true
          return { output: "consumer-done" }
        }
        return { output: "other" }
      },
      sealCandidate: async () => ({
        candidate: candSubject,
        taskId: taskAId,
        receipt: {
          receiptId: "receipt-1",
          runId: "run-dag-art",
          authorityRef: setup.authority.ref,
          candidate: candSubject,
          baselineHash: "d".repeat(64),
          patchHash: "e".repeat(64),
        },
        files: [{ path: "test.txt", beforeHash: "f".repeat(64), afterHash: "1".repeat(64) }],
      }),
    })

    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    // Delegate producer task A (keeps running)
    const delA = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-prod-a",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [{ clientTaskKey: "producer-a", objective: "Produce artifact", requestedCapabilities: ["read", "mutate"], dependsOn: [] }],
      },
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(taskAId).toBeTruthy()

    // Delegate consumer task C depending on A when: "artifact_produced"
    const delC = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-cons-c",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "consumer-c",
            objective: "Consume artifact",
            requestedCapabilities: ["read"],
            dependsOn: [{ taskId: taskAId, when: "artifact_produced" }],
          },
        ],
      },
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(taskCStarted).toBe(false)

    // Task A (still running) submits a mutating invoke to seal a candidate
    const invokeRes = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-mutate-a",
      basis: run.basis(taskAId),
      observationIds: [],
      action: { kind: "invoke", toolId: "mutate_file", arguments: { path: "test.txt" } },
    })
    expect(invokeRes.accepted).toBe(true)

    await new Promise((r) => setTimeout(r, 30))

    // Consumer C MUST now be unblocked and settled, EVEN THOUGH Task A is STILL running!
    expect(taskCStarted).toBe(true)
    let snap = run.snapshot()
    expect(snap.tasks.find((t) => t.clientTaskKey === "consumer-c")?.state).toBe("settled")
    expect(snap.tasks.find((t) => t.clientTaskKey === "producer-a")?.state).toBe("running")

    // Now unblock task A
    unblockA()
    await delA
    await delC
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: DAG dependency - when 'applied' unblocks immediately upon candidate apply", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-dag-applied-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-dag-applied", root, "root-task", { maxParallelTasks: 4 })
    let taskAId = ""
    let taskDStarted = false
    let unblockA: () => void = () => {}

    const candSubject: SubjectRef & { kind: "candidate" } = {
      id: "cand-app-1",
      revision: 1,
      sha256: "c".repeat(64),
      kind: "candidate",
    }
    setup.subjects.push(candSubject)

    const ports = createDefaultPorts(root, {
      resolveEffects: async (action) => {
        if (action.kind === "invoke" || action.kind === "apply_candidate") {
          return [{ operation: "mutate", targets: [{ kind: "workspace_path", selector: root }] }]
        }
        return []
      },
      beginMutation: async () => {},
      executeTask: async (task) => {
        if (task.proposal.clientTaskKey === "producer-app") {
          taskAId = task.taskId
          await new Promise<void>((resolve) => { unblockA = resolve })
          return { output: "producer-done" }
        }
        if (task.proposal.clientTaskKey === "wait-apply") {
          taskDStarted = true
          return { output: "wait-apply-done" }
        }
        return { output: "other" }
      },
      applyCandidate: async () => ({
        candidate: candSubject,
        state: "applied",
        unresolvedEffects: [],
      }),
      sealCandidate: async () => ({
        candidate: candSubject,
        taskId: taskAId,
        receipt: {
          receiptId: "receipt-app-1",
          runId: "run-dag-applied",
          authorityRef: setup.authority.ref,
          candidate: candSubject,
          baselineHash: "d".repeat(64),
          patchHash: "e".repeat(64),
        },
        files: [{ path: "test.txt", beforeHash: "f".repeat(64), afterHash: "1".repeat(64) }],
      }),
    })

    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    // 1. Delegate producer task A (in-flight)
    const delA = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-prod",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [{ clientTaskKey: "producer-app", objective: "Produce", requestedCapabilities: ["read", "mutate"], dependsOn: [] }],
      },
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(taskAId).toBeTruthy()

    // 2. While Task A is active, seal candidate via mutating invoke
    const sealRes = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-seal-cand",
      basis: run.basis(taskAId),
      observationIds: [],
      action: { kind: "invoke", toolId: "mutate_file", arguments: {} },
    })
    expect(sealRes.accepted).toBe(true)

    // Unblock task A to settle
    unblockA()
    await delA

    // 3. Delegate consumer task D waiting on A when: "applied"
    const delD = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-wait-app",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          {
            clientTaskKey: "wait-apply",
            objective: "Wait until candidate applied",
            requestedCapabilities: ["read"],
            dependsOn: [{ taskId: taskAId, when: "applied" }],
          },
        ],
      },
    })
    await new Promise((r) => setTimeout(r, 20))

    // Candidate is sealed, but NOT yet applied! Task D must remain pending
    expect(taskDStarted).toBe(false)
    let snap = run.snapshot()
    expect(snap.tasks.find((t) => t.clientTaskKey === "wait-apply")?.state).toBe("pending")

    // 4. Submit apply_candidate
    const applyRes = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-apply-cand",
      basis: run.basis("root-task"),
      observationIds: [],
      action: { kind: "apply_candidate", candidate: candSubject },
    })
    expect(applyRes.accepted).toBe(true)

    await delD
    await new Promise((r) => setTimeout(r, 30))

    // Task D MUST now be dispatched and settled!
    expect(taskDStarted).toBe(true)
    snap = run.snapshot()
    expect(snap.tasks.find((t) => t.clientTaskKey === "wait-apply")?.state).toBe("settled")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: amend_tasks - replace_pending, cancel, and add operations", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-amend-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-amend", root, "root-task", { maxParallelTasks: 1 })
    let unblockT1: () => void = () => {}
    let task1Cancelled = false

    const ports = createDefaultPorts(root, {
      executeTask: async (task) => {
        task.signal.addEventListener("abort", () => {
          task1Cancelled = true
          unblockT1()
        })
        if (task.proposal.clientTaskKey === "t1") {
          await new Promise<void>((resolve) => { unblockT1 = resolve })
          return { output: "t1-done" }
        }
        return { output: `done:${task.taskId}` }
      },
    })

    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    // Delegate t1 and t2 (maxParallelTasks: 1 -> t1 runs, t2 pending)
    const initDel = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-init-del",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          { clientTaskKey: "t1", objective: "T1 running", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "t2", objective: "T2 pending", requestedCapabilities: ["read"], dependsOn: [] },
        ],
      },
    })
    await new Promise((r) => setTimeout(r, 20))

    let snap = run.snapshot()
    const task1 = snap.tasks.find((t) => t.clientTaskKey === "t1")!
    const task2 = snap.tasks.find((t) => t.clientTaskKey === "t2")!
    expect(task1.state).toBe("running")
    expect(task2.state).toBe("pending")
    const initialRev = snap.graphRevision

    // 1. Stale revision check
    const staleAmend = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-stale-amend",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "amend_tasks",
        expectedGraphRevision: initialRev - 1,
        changes: [{ kind: "cancel", taskId: task1.taskId }],
      },
    })
    expect(staleAmend.accepted).toBe(false)
    expect(rejectionCode(staleAmend)).toBe("AUTONOMOUS_GRAPH_REVISION_STALE")

    // 2. replace_pending on a running task must fail
    const runningReplace = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-bad-replace",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "amend_tasks",
        expectedGraphRevision: initialRev,
        changes: [
          {
            kind: "replace_pending",
            taskId: task1.taskId,
            task: { clientTaskKey: "t1", objective: "Replaced T1", requestedCapabilities: ["read"], dependsOn: [] },
          },
        ],
      },
    })
    expect(runningReplace.accepted).toBe(false)
    expect(rejectionCode(runningReplace)).toBe("AUTONOMOUS_TASK_RUNNING_REPLACE")

    // 3. replace_pending on task2 (pending) succeeds
    const goodReplace = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-good-replace",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "amend_tasks",
        expectedGraphRevision: initialRev,
        changes: [
          {
            kind: "replace_pending",
            taskId: task2.taskId,
            task: { clientTaskKey: "t2-replaced", objective: "T2 new objective", requestedCapabilities: ["read"], dependsOn: [] },
          },
        ],
      },
    })
    expect(goodReplace.accepted).toBe(true)

    snap = run.snapshot()
    const updatedTask2 = snap.tasks.find((t) => t.taskId === task2.taskId)!
    expect(updatedTask2.clientTaskKey).toBe("t2-replaced")
    expect(updatedTask2.objective).toBe("T2 new objective")
    expect(updatedTask2.revision).toBe(2)
    expect(snap.graphRevision).toBe(initialRev + 1)

    // 4. Cancel running task1
    const cancelResult = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-cancel-t1",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "amend_tasks",
        expectedGraphRevision: snap.graphRevision,
        changes: [{ kind: "cancel", taskId: task1.taskId }],
      },
    })
    expect(cancelResult.accepted).toBe(true)
    expect(task1Cancelled).toBe(true)

    // 5. Add new task3 via amend_tasks
    snap = run.snapshot()
    const addResult = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-add-t3",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "amend_tasks",
        expectedGraphRevision: snap.graphRevision,
        changes: [
          {
            kind: "add",
            task: { clientTaskKey: "t3", objective: "Dynamically added T3", requestedCapabilities: ["read"], dependsOn: [] },
          },
        ],
      },
    })
    expect(addResult.accepted).toBe(true)

    snap = run.snapshot()
    expect(snap.tasks.some((t) => t.clientTaskKey === "t3")).toBe(true)
    await initDel
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: Cancellation and late result capture", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-late-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-late", root, "root-task")
    let lateTaskId = ""
    let finishLateTask: () => void = () => {}

    const ports = createDefaultPorts(root, {
      executeTask: async (task) => {
        lateTaskId = task.taskId
        task.signal.addEventListener("abort", () => {
          setTimeout(() => finishLateTask(), 10)
        })
        await new Promise<void>((resolve) => { finishLateTask = resolve })
        return { output: "late-output" }
      },
    })

    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    const del = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-delegate-late",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [{ clientTaskKey: "late-worker", objective: "Will be cancelled", requestedCapabilities: ["read"], dependsOn: [] }],
      },
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(lateTaskId).toBeTruthy()

    // Cancel task via amend_tasks while it is running
    const snap = run.snapshot()
    const cancelRes = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-cancel-late",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "amend_tasks",
        expectedGraphRevision: snap.graphRevision,
        changes: [{ kind: "cancel", taskId: lateTaskId }],
      },
    })
    expect(cancelRes.accepted).toBe(true)

    let currentSnap = run.snapshot()
    const task = currentSnap.tasks.find((t) => t.taskId === lateTaskId)!
    expect(task.state).toBe("cancelled")

    await del
    await new Promise((r) => setTimeout(r, 30))

    // Late result must be captured in lateResults without corrupting state to settled
    currentSnap = run.snapshot()
    expect(currentSnap.lateResultIds).toContain(lateTaskId)
    expect(currentSnap.tasks.find((t) => t.taskId === lateTaskId)?.state).toBe("cancelled")
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: Shared budget enforcement across parent and child tasks", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-budget-"))).replaceAll("\\", "/")
  try {
    const setup = createSetup("run-budget-shared", root, "root-task", { maxActions: 3 })
    let childTaskId = ""
    let unblockChild: () => void = () => {}

    const ports = createDefaultPorts(root, {
      executeTask: async (task) => {
        childTaskId = task.taskId
        await new Promise<void>((resolve) => { unblockChild = resolve })
        return { output: "child-alive" }
      },
    })

    const run = new AutonomousRun(setup, ports)
    run.prepare({ status: "proceed", context: {} })

    // Action 1: Delegate (child is running in background)
    const del = run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-shared-1",
      basis: run.basis("root-task"),
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [{ clientTaskKey: "b-child", objective: "Budget child", requestedCapabilities: ["read"], dependsOn: [] }],
      },
    })
    await new Promise((r) => setTimeout(r, 20))
    expect(childTaskId).toBeTruthy()

    // Action 2: Invoke by child (child is running)
    const inv1 = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-shared-2",
      basis: run.basis(childTaskId),
      observationIds: [],
      action: { kind: "invoke", toolId: "read", arguments: {} },
    })
    expect(inv1.accepted).toBe(true)

    // Action 3: Invoke by root (reaches maxActions: 3)
    const inv2 = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-shared-3",
      basis: run.basis("root-task"),
      observationIds: [],
      action: { kind: "invoke", toolId: "read", arguments: {} },
    })
    expect(inv2.accepted).toBe(true)

    // Action 4: Exceeds shared budget!
    const inv3 = await run.submit({
      schemaVersion: "decision-v1",
      decisionId: "dec-shared-4",
      basis: run.basis(childTaskId),
      observationIds: [],
      action: { kind: "invoke", toolId: "read", arguments: {} },
    })
    expect(inv3.accepted).toBe(false)
    expect(["AUTONOMOUS_RESOURCE_FAILURE", "AUTONOMOUS_BUDGET_EXHAUSTED", "RESOURCE_EXHAUSTED", "BUDGET_EXHAUSTED"]).toContain(rejectionCode(inv3))

    unblockChild()
    await del
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})

test("M4-B: End-to-end delegation through CoordinatorRuntime", async () => {
  const root = (await mkdtemp(join(tmpdir(), "m4b-coord-runtime-"))).replaceAll("\\", "/")
  const runtime = new CoordinatorRuntime(async () => { throw new Error("legacy verifier must not start") }, {
    repository: new RunRepository({ persistent: false, stateDirectory: join(root, "history") }),
  })

  try {
    const opened = await runtime.openRun({
      sessionID: "coord-session",
      workspace: root,
      goal: "Investigate subtask delegation",
      autonomousFactory: async (runId) => {
        const setup = createSetup(runId, root, "coord-session", { maxParallelTasks: 2, maxTotalTasks: 5 })
        const ports = createDefaultPorts(root, {
          executeTask: async (task) => {
            return {
              sessionId: `sub-session-${task.taskId}`,
              output: `handled:${task.proposal.objective}`,
            }
          },
        })
        return { setup, ports }
      },
    })

    expect(opened.autonomous?.lifecycle).toBe("preparing")
    await runtime.prepareAutonomous("coord-session", opened.runId, { status: "proceed", context: {} })

    // Root delegates two subtasks
    const basis = runtime.autonomousBasis("coord-session", opened.runId)
    const delResult = await runtime.submitAutonomousDecision("coord-session", opened.runId, {
      schemaVersion: "decision-v1",
      decisionId: "dec-coord-del",
      basis,
      observationIds: [],
      action: {
        kind: "delegate",
        tasks: [
          { clientTaskKey: "sub-1", objective: "Analyze logs", requestedCapabilities: ["read"], dependsOn: [] },
          { clientTaskKey: "sub-2", objective: "Inspect dependencies", requestedCapabilities: ["read"], dependsOn: [] },
        ],
      },
    })
    expect(delResult.accepted).toBe(true)

    // Wait for subtasks to settle
    await new Promise((r) => setTimeout(r, 40))

    const status = runtime.status("coord-session")
    expect(status.autonomous?.tasks.length).toBe(3) // root + 2 subtasks
    expect(status.autonomous?.tasks.every((t) => t.state === "settled" || t.state === "running")).toBe(true)

    // Finish the run
    const finishResult = await runtime.submitAutonomousDecision("coord-session", opened.runId, {
      schemaVersion: "decision-v1",
      decisionId: "dec-finish",
      basis: runtime.autonomousBasis("coord-session", opened.runId),
      observationIds: [],
      action: {
        kind: "finish",
        openWork: "drain",
        report: { ...ref("report"), kind: "report" },
        assessment: { status: "satisfied", summary: "Delegation successful", citedObservationIds: [], uncertainties: [] },
      },
    })
    expect(finishResult.accepted).toBe(true)

    const finalStatus = runtime.status("coord-session")
    expect(finalStatus.autonomous?.completion?.reason).toBe("requested")
    expect(finalStatus.autonomous?.completion?.assessment?.status).toBe("satisfied")
  } finally {
    await runtime.closeWorkspace(root)
    runtime.resetForTest()
    await rm(root, { recursive: true, force: true })
  }
})
