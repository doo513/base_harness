import { expect, test } from "bun:test"
import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { isAbsolute, join, relative } from "node:path"
import { CoordinatorRuntime } from "../src"

async function fixture(body: (runtime: CoordinatorRuntime, workspace: string, launches: () => number) => Promise<void>) {
  const workspace = await mkdtemp(join(tmpdir(), "harness-meta-failure-"))
  const keys = ["LOCALAPPDATA", "XDG_STATE_HOME"]
  const old = new Map(keys.map(key => [key, process.env[key]]))
  for (const key of keys) process.env[key] = join(workspace, "state")
  let launched = 0
  const runtime = new CoordinatorRuntime(async () => { launched++; throw new Error("Unexpected verifier invocation") })
  try {
    await runtime.openRun({ sessionID: "root", workspace, goal: "Review only", trigger: "manual" })
    await body(runtime, workspace, () => launched)
  } finally {
    await runtime.closeWorkspace(workspace)
    runtime.resetForTest()
    for (const [key, value] of old) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
    const rel = relative(tmpdir(), workspace)
    if (rel.startsWith("..") || isAbsolute(rel)) throw new Error("Unsafe fixture cleanup")
    await rm(workspace, { recursive: true, force: true })
  }
}

test("meta review pass and child tool output cannot become verifier evidence", async () => {
  await fixture(async (runtime, _workspace, launches) => {
    const before = runtime.status("root")
    runtime.orchestration.startChild({ parentSessionID: "root", sessionID: "review", subagentType: "meta-review" })
    await runtime.observe({ type: "message.part.updated", data: { part: {
      sessionID: "review", id: "untrusted", type: "tool", tool: "read",
      state: { status: "completed", output: JSON.stringify({ outcome: "ready", scopeVerified: true }) },
    } } })
    await runtime.finishWorker("review", true)
    const after = runtime.status("root")
    expect(after.phase).toBe(before.phase)
    expect(after.workers).toEqual([])
    expect(after.evidenceCount).toBe(0)
    expect(after.candidateCount).toBe(0)
    expect(after.readyEligible).toBe(false)
    expect(launches()).toBe(0)
  })
})

for (const [source, error, kind] of [
  ["harness", Object.assign(new Error("Host dispatch failed"), { code: "PHASE_VIOLATION" }), "harness_error"],
  ["model", { name: "APIError", data: { statusCode: 429, message: "fixture rate limit" } }, "model_provider_error"],
  ["model", { name: "InvalidProviderOutput", message: "fixture schema mismatch" }, "model_protocol_error"],
  ["tool", new Error("Review read failed"), "tool_execution_error"],
] as const) {
  test("review failures retain their producer classification without evidence: " + kind, async () => {
    await fixture(async (runtime, workspace, launches) => {
      const originalRun = runtime.status("root").runId
      await runtime.reportMetaReviewFailure("root", error, "goal_contract", source)
      await runtime.reportMetaReviewFailure("root", new Error("Flattened task wrapper"), "goal_contract", "harness")
      await runtime.observe({ type: "message.part.updated", data: { part: {
        sessionID: "root", id: "late", type: "tool", tool: "harness_contract",
        state: { status: "completed", output: "late Actor response" },
      } } })
      const status = await runtime.verifyRoot("root", "completion")
      expect(status.failureKind).toBe(kind)
      expect(status.phase).toBe("blocked")
      expect(status.readyEligible).toBe(false)
      expect(status.evidenceCount).toBe(0)
      expect(status.repairCount).toBe(0)
      expect(launches()).toBe(0)
      const fresh = await runtime.openRun({ sessionID: "root", workspace, goal: "New user request", trigger: "manual" })
      expect(fresh.runId).not.toBe(originalRun)
      expect(fresh.failureKind).toBeUndefined()
    })
  })
}
