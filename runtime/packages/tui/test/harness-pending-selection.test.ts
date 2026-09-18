import { afterEach, expect, test } from "bun:test"
import { flushPendingHarnessControls, pendingHarnessSelection, queueHarnessControl } from "../src/harness/pending-control"

afterEach(async () => { await flushPendingHarnessControls(async () => ({})) })

test("pending custom selections show unvalidated intent without choosing a fallback domain", async () => {
  queueHarnessControl({ type: "domain.set", domain: "research.Custom" })
  queueHarnessControl({ type: "skill.set", skill: "review", enabled: true })
  queueHarnessControl({ type: "skill.set", skill: "report", enabled: true })
  queueHarnessControl({ type: "skill.set", skill: "review", enabled: false })
  expect(pendingHarnessSelection()).toMatchObject({ domain: "research.Custom", skills: ["report"], count: 3 })
  const sent: unknown[] = []
  await flushPendingHarnessControls(async (control) => { sent.push(control); return {} })
  expect(sent).toEqual([
    { type: "domain.set", domain: "research.Custom" },
    { type: "skill.set", skill: "report", enabled: true },
    { type: "skill.set", skill: "review", enabled: false },
  ])
  expect(pendingHarnessSelection().count).toBe(0)
})

test("Hackathon alias intent does not locally switch General to Develop", () => {
  queueHarnessControl({ type: "domain.set", domain: "general" })
  queueHarnessControl({ type: "skill.set", skill: "hackathon", enabled: true })
  expect(pendingHarnessSelection()).toMatchObject({ domain: "general", skills: ["hackathon"] })
})

test("a failed Host control stops setup and preserves the complete new-session selection for retry", async () => {
  queueHarnessControl({ type: "domain.set", domain: "research" })
  queueHarnessControl({ type: "skill.set", skill: "unknown", enabled: true })
  queueHarnessControl({ type: "planning.plan_once" })
  const sent: string[] = []
  await expect(flushPendingHarnessControls(async (control) => {
    sent.push(control.type)
    return control.type === "skill.set"
      ? { error: { kind: "OVERLAY_UNKNOWN", message: "Overlay is not registered." }, response: { status: 400 } }
      : { data: { phase: "inactive" } }
  })).rejects.toThrow("OVERLAY_UNKNOWN")
  expect(sent).toEqual(["domain.set", "skill.set"])
  expect(pendingHarnessSelection()).toMatchObject({ domain: "research", skills: ["unknown"], planOnce: true, count: 3 })
})

test("controls staged during a request remain queued for the next new session", async () => {
  queueHarnessControl({ type: "domain.set", domain: "first" })
  const entered = Promise.withResolvers<void>()
  const release = Promise.withResolvers<void>()
  const sending = flushPendingHarnessControls(async () => { entered.resolve(); await release.promise; return {} })
  await entered.promise
  queueHarnessControl({ type: "domain.set", domain: "second" })
  release.resolve()
  await sending
  expect(pendingHarnessSelection()).toMatchObject({ domain: "second", count: 1 })
})
