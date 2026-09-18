import { expect, test } from "bun:test"
import { AutonomousBudget } from "../src/autonomous-budget"

const now = Date.parse("2026-09-18T00:00:00Z")
const limits = { deadlineAt: "2026-09-18T01:00:00Z", maxActions: 2, maxParallelTasks: 2, maxTaskDepth: 3, maxTotalTasks: 8, maxModelTokens: 100, maxCost: { currency: "USD", minorUnits: 20 } }
const zero = { modelTokens: 0, costMinorUnits: 0 }
const create = () => new AutonomousBudget("budget", limits, { tokens: true, cost: true }, () => now)

test("concurrent admissions atomically reserve the last action", async () => {
  const ledger = create()
  const results = await Promise.allSettled([1, 2, 3].map(async (id) => ledger.reserve(String(id), { id }, zero)))
  expect(results.filter((result) => result.status === "fulfilled")).toHaveLength(2)
  expect(ledger.snapshot().actions).toBe(2)
})
test("same request and canonical payload replay without cost; changed payload conflicts", () => {
  const ledger = create()
  expect(ledger.reserve("id", { b: 2, a: 1 }, zero)).toBe("reserved")
  expect(ledger.reserve("id", { a: 1, b: 2 }, zero)).toBe("replay")
  expect(() => ledger.reserve("id", { a: 2 }, zero)).toThrow("REQUEST_CONFLICT")
  ledger.settle("id", zero)
  expect(ledger.reserve("id", { a: 1, b: 2 }, zero)).toBe("replay")
  expect(ledger.snapshot().actions).toBe(1)
})
test("model Prepare and subsequent actions share cumulative reservations", () => {
  const ledger = create()
  ledger.reserve("prepare", { phase: "prepare" }, { modelTokens: 60, costMinorUnits: 15 })
  expect(() => ledger.reserve("execute", {}, { modelTokens: 50, costMinorUnits: 0 })).toThrow("BUDGET_EXHAUSTED")
  expect(() => ledger.reserve("execute", {}, { modelTokens: 0, costMinorUnits: 6 })).toThrow("BUDGET_EXHAUSTED")
  ledger.settle("prepare", { modelTokens: 40, costMinorUnits: 10 })
  ledger.reserve("execute", {}, { modelTokens: 60, costMinorUnits: 10 })
  expect(ledger.snapshot().used.modelTokens + ledger.snapshot().reserved.modelTokens).toBe(100)
})
test("cancelled/no-use actions still count and limits cannot be changed through snapshots", () => {
  const ledger = create()
  ledger.reserve("cancelled", {}, zero); ledger.settle("cancelled", zero)
  ledger.reserve("other", {}, zero); ledger.settle("other", zero)
  const snapshot = ledger.snapshot(); snapshot.limits.maxActions = 100
  expect(() => ledger.reserve("third", {}, zero)).toThrow("BUDGET_EXHAUSTED")
})
test("deadline remains active while waiting; cleanup settlement is still allowed", () => {
  let clock = now
  const ledger = new AutonomousBudget("budget", limits, { tokens: true, cost: true }, () => clock)
  ledger.reserve("id", {}, zero)
  clock = Date.parse(limits.deadlineAt)
  expect(() => ledger.reserve("late", {}, zero)).toThrow("DEADLINE_EXCEEDED")
  expect(() => ledger.settle("id", zero)).not.toThrow()
})
test("metering overruns latch a fault, no further paid work can be admitted", () => {
  const ledger = create()
  ledger.reserve("id", {}, { modelTokens: 10, costMinorUnits: 2 })
  expect(() => ledger.settle("id", { modelTokens: 11, costMinorUnits: 2 })).toThrow("METERING_OVERRUN")
  expect(() => ledger.reserve("new", {}, zero)).toThrow("METERING_FAULT")
  expect(ledger.snapshot().faulted).toBe(true)
})
test("settlement is idempotent but cannot be revised to erase usage", () => {
  const ledger = create()
  const used = { modelTokens: 10, costMinorUnits: 2 }
  ledger.reserve("id", {}, used); ledger.settle("id", used); ledger.settle("id", used)
  expect(() => ledger.settle("id", zero)).toThrow("SETTLEMENT_CONFLICT")
  expect(ledger.snapshot().used).toEqual(used)
})

test("action-only limits still record reported usage without claiming an unsupported hard cap", () => {
  const { maxModelTokens, maxCost, ...actionLimits } = limits
  const ledger = new AutonomousBudget("actions-only", actionLimits, { tokens: false, cost: false }, () => now)
  ledger.reserve("model", {}, zero)
  ledger.settle("model", { modelTokens: 37, costMinorUnits: 2 })
  expect(ledger.snapshot().used).toEqual({ modelTokens: 37, costMinorUnits: 2 })
  expect(ledger.snapshot().faulted).toBe(false)
})

test("an interrupted provider settlement preserves known usage and marks it incomplete", () => {
  const { maxModelTokens, maxCost, ...actionLimits } = limits
  const ledger = new AutonomousBudget("incomplete", actionLimits, { tokens: false, cost: false }, () => now)
  ledger.reserve("model", {}, zero)
  ledger.settle("model", { modelTokens: 3, costMinorUnits: 0, complete: false })
  expect(ledger.snapshot().used).toEqual({ modelTokens: 3, costMinorUnits: 0 })
  expect(ledger.snapshot().incompleteSettlementIds).toEqual(["model"])
})
