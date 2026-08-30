import { expect, test } from "bun:test"
import {
  closeExplorationBudget,
  consumeExplorationBudget,
  EXPLORATION_ALLOWED_TOOLS,
  EXPLORATION_DENIED_TOOLS,
  ExplorationBudgetExceeded,
  explorationBudgetStatus,
  normalizeExplorationRequest,
  openExplorationBudget,
} from "../../src/tool/exploration-budget"

test("preset overrides can only reduce exploration budgets", () => {
  expect(normalizeExplorationRequest({ thoroughness: "quick", maxToolCalls: 99, maxFiles: 99 })).toEqual({
    thoroughness: "quick",
    maxToolCalls: 8,
    maxFiles: 12,
  })
  expect(normalizeExplorationRequest({ thoroughness: "deep", maxToolCalls: 7, maxFiles: 9 })).toEqual({
    thoroughness: "deep",
    maxToolCalls: 7,
    maxFiles: 9,
  })
})

test("exploration excludes mutating, shell, web, and delegation tools", () => {
  expect(EXPLORATION_ALLOWED_TOOLS).toEqual(["read", "grep", "glob", "list"])
  expect(EXPLORATION_DENIED_TOOLS).toEqual([
    "bash",
    "shell",
    "argv",
    "write",
    "edit",
    "apply_patch",
    "task",
    "webfetch",
    "websearch",
  ])
})

test("budget exhaustion returns partial state and terminates after a repeated call", () => {
  const session = "explore-budget"
  openExplorationBudget(session, { thoroughness: "quick", maxToolCalls: 2 })
  consumeExplorationBudget(session, "glob")
  consumeExplorationBudget(session, "read", "a.ts")

  let first: ExplorationBudgetExceeded | undefined
  try {
    consumeExplorationBudget(session, "read", "b.ts")
  } catch (error) {
    first = error as ExplorationBudgetExceeded
  }
  expect(first).toBeInstanceOf(ExplorationBudgetExceeded)
  expect(first?.terminal).toBe(false)
  expect(first?.status.truncated).toBe(true)

  expect(() => consumeExplorationBudget(session, "grep")).toThrow(ExplorationBudgetExceeded)
  expect(explorationBudgetStatus(session)?.violations).toBe(2)
  closeExplorationBudget(session)
  expect(explorationBudgetStatus(session)).toBeUndefined()
})

test("unique read file limits are enforced independently of call presets", () => {
  const session = "explore-files"
  openExplorationBudget(session, { thoroughness: "quick", maxFiles: 1 })
  consumeExplorationBudget(session, "read", "a.ts")
  expect(() => consumeExplorationBudget(session, "read", "b.ts")).toThrow(ExplorationBudgetExceeded)
  closeExplorationBudget(session)
})
