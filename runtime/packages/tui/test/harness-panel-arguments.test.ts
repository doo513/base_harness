import { expect, test } from "bun:test"
import { harnessPanelLayout, harnessPlanningCue, nextRequestPlanOnly } from "../src/harness/panel-presentation"
import { resolveLocalSlash } from "../src/prompt/local-slash"

const commands = [
  { display: "/plan" },
  { display: "/plan discard" },
  { display: "/execute", argument: "planId", aliases: ["/run-reviewed"] },
  { display: "/harness" },
]

test("execute forwards one opaque plan ID without rewriting its case or spelling", () => {
  const result = resolveLocalSlash("/execute Plan-ABC_123", commands)
  expect(result?.kind).toBe("command")
  if (result?.kind !== "command") throw new Error("Expected registered command")
  expect(result.command.display).toBe("/execute")
  expect(result.arguments).toEqual(["Plan-ABC_123"])
})

test("execute without an ID and aliases share the same command contract", () => {
  const current = resolveLocalSlash("/execute", commands)
  const alias = resolveLocalSlash("/run-reviewed plan-1", commands)
  expect(current?.kind === "command" ? current.arguments : null).toEqual([])
  expect(alias?.kind === "command" ? alias.arguments : null).toEqual(["plan-1"])
})

test("a longer multiword command wins over its shorter prefix", () => {
  const result = resolveLocalSlash("/plan discard", commands)
  expect(result?.kind === "command" ? result.command.display : null).toBe("/plan discard")
  expect(resolveLocalSlash("/plan discard more", commands)).toEqual({ kind: "invalid", usage: "/plan discard" })
})

for (const input of ["/execute one two", "/execute\nplan-1", "/execute plan-1\nextra", "/plan build an app", "/harness extra"]) {
  test("malformed registered control stays out of the ordinary prompt path: " + JSON.stringify(input), () => {
    expect(resolveLocalSlash(input, commands)?.kind).toBe("invalid")
  })
}

test("normal prose and unknown slash names are not interpreted as execution permission", () => {
  for (const input of ["please /execute plan-1", "implement the plan", "/unknown", "/executed plan-1"]) {
    expect(resolveLocalSlash(input, commands)).toBeUndefined()
  }
})

test("horizontal token whitespace is accepted without shell parsing", () => {
  const result = resolveLocalSlash(" /execute\tplan-1  ", commands)
  expect(result?.kind === "command" ? result.arguments : null).toEqual(["plan-1"])
  expect(resolveLocalSlash('/execute "two words"', commands)?.kind).toBe("invalid")
})

for (const [columns, rows] of [[40, 10], [80, 24], [120, 40], [200, 60]]) {
  test("overlay reserves a bounded viewport and fixed header/footer: " + columns + "x" + rows, () => {
    const layout = harnessPanelLayout(columns!, rows!)
    expect(layout.width).toBeLessThanOrEqual(columns! - 4)
    expect(layout.width).toBeLessThanOrEqual(64)
    expect(layout.height).toBe(rows! - 3)
    expect(layout.bodyHeight + 4).toBe(layout.height)
    expect(layout.bodyHeight).toBeGreaterThan(0)
  })
}

test("an existing session uses the Host planning preference, not the home staging queue", () => {
  expect(nextRequestPlanOnly({ sessionID: "root", planningPreference: "plan_once" }, false)).toBe(true)
  expect(nextRequestPlanOnly({ sessionID: "root", planningPreference: "auto" }, true)).toBe(false)
  expect(nextRequestPlanOnly({ sessionID: "" }, true)).toBe(true)
  expect(nextRequestPlanOnly({}, false)).toBe(false)
})

for (const planningState of [
  "contract_building", "contract_preflight", "contract_reviewing", "awaiting_input",
  "planning_decision", "plan_building", "plan_reviewing",
]) {
  test("active plan-only is not advertised as the next request: " + planningState, () => {
    const status = { sessionID: "root", planningPreference: "plan_once" as const, planOnly: true, planningState }
    expect(nextRequestPlanOnly(status, true)).toBe(false)
    expect(harnessPlanningCue(status, true)?.kind).toBe("active")
    expect(harnessPlanningCue({ ...status, planOnly: false }, true)).toBeUndefined()
  })
}

test("review, recovery, and execution labels do not claim a pending next request", () => {
  expect(harnessPlanningCue({ sessionID: "root", planningState: "plan_ready" }, false)?.kind).toBe("reviewed")
  expect(harnessPlanningCue({
    sessionID: "root", planningState: "plan_ready", planRecovery: { code: "PLAN_REVISION_PENDING" },
  }, false)?.kind).toBe("recovery")
  expect(harnessPlanningCue({ sessionID: "root", planningState: "executing", planOnly: false }, true)).toBeUndefined()
  expect(harnessPlanningCue({ sessionID: "root", planningState: "idle", planningPreference: "plan_once" }, false)?.kind).toBe("next")
})

test("terminal failures and unknown future states are not shown as active plan building", () => {
  for (const phase of ["blocked", "interrupted", "failure", "ready"]) {
    expect(harnessPlanningCue({ sessionID: "root", phase, planningState: "plan_building", planOnly: true }, true)).toBeUndefined()
  }
  expect(harnessPlanningCue({
    sessionID: "root", planningState: "future_state", planningPreference: "plan_once", planOnly: true,
  }, true)).toBeUndefined()
})

test("a blocked reviewed plan never advertises execute as the next action", () => {
  for (const phase of ["blocked", "interrupted", "failure"]) {
    const cue = harnessPlanningCue({ sessionID: "root", phase, planningState: "plan_ready", planOnly: true }, true)
    expect(cue?.kind).toBe("blocked")
    expect(cue?.label).not.toContain("/execute")
    expect(cue?.message).toContain("Host run is blocked")
  }
})
