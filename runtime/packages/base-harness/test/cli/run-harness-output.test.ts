import { expect, test } from "bun:test"
import {
  assertExecutePlanOptions, headlessControls, harnessEventStatus,
  harnessExitCode, harnessSettled, unwrapHarnessStatus,
} from "../../src/cli/cmd/run/harness-output"

const status = (values: Record<string, unknown> = {}) => ({
  sessionID: "root", phase: "planning", readyEligible: false, planningState: "plan_ready", ...values,
})

test("resumption does not implicitly reset domain or skills", () => {
  expect(headlessControls({})).toEqual([])
  expect(headlessControls({ executePlan: "reviewed" })).toEqual([])
  expect(headlessControls({ plan: true })).toEqual([{ type: "planning.plan_once" }])
  expect(headlessControls({ domain: "develop", hackathon: true, plan: true })).toEqual([
    { type: "domain.set", domain: "develop" },
    { type: "skill.set", skill: "hackathon", enabled: true },
    { type: "planning.plan_once" },
  ])
})

test("custom identifiers and multiple overlay edits reach the Host without builtin filtering", () => {
  expect(headlessControls({
    domain: "research.Custom", overlay: ["review", "report"], disableOverlay: ["legacy"],
  })).toEqual([
    { type: "domain.set", domain: "research.Custom" },
    { type: "skill.set", skill: "review", enabled: true },
    { type: "skill.set", skill: "report", enabled: true },
    { type: "skill.set", skill: "legacy", enabled: false },
  ])
})

test("explicit external execution settings are forwarded as a Host control", () => {
  expect(headlessControls({ executionBackend: "custom", executionModel: "Exact-ID", executionEffort: "high" }))
    .toEqual([{
      type: "execution.select",
      selection: { adapterID: "custom", modelID: "Exact-ID", options: { reasoning_effort: "high" } },
    }])
})

test("execution resolves the reviewed session and cannot replace reviewed settings", () => {
  expect(() => assertExecutePlanOptions({ executePlan: "plan" })).not.toThrow()
  expect(() => assertExecutePlanOptions({ executePlan: "plan", session: "root" })).not.toThrow()
  for (const override of [
    { domain: "general" as const }, { hackathon: true }, { plan: true }, { model: "provider/model" },
    { variant: "native-max" }, { agent: "different" }, { fork: true }, { command: "build" }, { message: "new goal" },
    { overlay: ["review"] }, { disableOverlay: ["review"] }, { executionBackend: "external" },
    { executionModel: "another" }, { executionEffort: "high" },
  ]) {
    expect(() => assertExecutePlanOptions({ executePlan: "plan", session: "root", ...override })).toThrow("reviewed plan")
  }
})

test("SDK errors and malformed responses cannot become a successful Host status", () => {
  expect(unwrapHarnessStatus({ data: status() })).toEqual(status())
  expect(unwrapHarnessStatus(status())).toEqual(status())
  expect(() => unwrapHarnessStatus({ error: { code: "PLAN_STALE" }, data: status() })).toThrow("Host rejected")
  for (const value of [undefined, {}, { data: null }, { data: { sessionID: "root", phase: "ready" } }]) {
    expect(() => unwrapHarnessStatus(value)).toThrow("HARNESS_STATUS_INVALID")
  }
})

test("only the root Host status event controls headless completion", () => {
  expect(harnessEventStatus({ type: "harness.status", properties: { status: status() } }, "root")).toEqual(status())
  expect(harnessEventStatus({ type: "tool", properties: { status: status() } }, "root")).toBeUndefined()
  expect(harnessEventStatus({ type: "harness.status", properties: { status: status({ sessionID: "child" }) } }, "root")).toBeUndefined()
  expect(harnessSettled(status(), true)).toBe(true)
  expect(harnessSettled(status(), false)).toBe(false)
  expect(harnessSettled(status({ phase: "blocked" }), false)).toBe(true)
  expect(harnessSettled(status({ phase: "autonomous", autonomous: { lifecycle: "active" } }), false)).toBe(false)
  expect(harnessSettled(status({ phase: "autonomous", autonomous: { lifecycle: "closed" } }), false)).toBe(true)
  expect(harnessSettled(status({ phase: "worker_running", outcome: "repair_exhausted" }), false)).toBe(false)
})

test("headless exit codes distinguish legacy Ready, model satisfaction, partial results, and runtime failure", () => {
  expect(harnessExitCode(status(), true)).toBe(0)
  expect(harnessExitCode(status(), false)).toBe(1)
  expect(harnessExitCode(status({ phase: "ready", outcome: "ready", readyEligible: true }), false)).toBe(0)
  expect(harnessExitCode(status({ phase: "direct", outcome: "ready", readyEligible: true }), false)).toBe(1)
  expect(harnessExitCode(status({ phase: "ready", outcome: "ready" }), false)).toBe(1)
  expect(harnessExitCode(status({ phase: "autonomous", autonomous: { lifecycle: "closed",
    completion: { reason: "requested", assessment: { status: "satisfied" } } } }), false)).toBe(0)
  for (const assessment of ["partial", "unsolved", "not_assessed"] as const) {
    expect(harnessExitCode(status({ phase: "autonomous", autonomous: { lifecycle: "closed",
      completion: { reason: "requested", assessment: { status: assessment } } } }), false)).toBe(2)
  }
  expect(harnessExitCode(status({ phase: "autonomous", autonomousResult: {
    lifecycle: "closed", runtimeReason: "requested", assessment: { status: "partial" }, observations: [],
  } }), false)).toBe(2)
  for (const reason of ["cancelled", "budget_exhausted", "deadline_exceeded", "runtime_fault", "interrupted"] as const) {
    expect(harnessExitCode(status({ phase: "autonomous", autonomous: { lifecycle: "closed",
      completion: { reason, assessment: null } } }), false)).toBe(1)
  }
  for (const phase of ["blocked", "interrupted", "failure"]) {
    expect(harnessExitCode(status({ phase }), true)).toBe(1)
    expect(harnessExitCode(status({ phase }), false)).toBe(1)
  }
})
