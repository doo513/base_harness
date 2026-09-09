import { expect, test } from "bun:test"
import { createHarnessStatusBinding, harnessRootSession } from "../src/harness/session-status"
import { matchLocalSlash } from "../src/prompt/local-slash"

type Status = { sessionID: string; phase: string; planRecovery?: { code: string } }

function fixture() {
  const requests: Array<{ target: { sessionID: string; directory?: string }; result: ReturnType<typeof Promise.withResolvers<Status>> }> = []
  const published: Status[] = []
  let resets = 0
  const binding = createHarnessStatusBinding<Status>({
    fetch(target) {
      const result = Promise.withResolvers<Status>()
      requests.push({ target, result })
      return result.promise
    },
    publish: (status) => { published.push(status) },
    reset: () => { resets += 1 },
  })
  return { binding, requests, published, resets: () => resets }
}

test("an attached root hydrates recovery state without mounting a sidebar", async () => {
  const f = fixture()
  f.binding.select({ sessionID: "root", directory: "/workspace" })
  const fetching = f.binding.refresh()
  const pending = { sessionID: "root", phase: "blocked", planRecovery: { code: "PLAN_REVISION_PENDING" } }
  f.requests[0]!.result.resolve(pending)
  expect(await fetching).toEqual(pending)
  expect(f.published).toEqual([pending])
  expect(f.resets()).toBe(1)
})

test("a child route resolves its root and cycles never pick another session", () => {
  const sessions: Record<string, { parentID?: string }> = { child: { parentID: "root" }, root: {} }
  expect(harnessRootSession("child", (id) => sessions[id])).toBe("root")
  expect(harnessRootSession(undefined, () => undefined)).toBeUndefined()
  expect(harnessRootSession("cold", () => undefined)).toBe("cold")
  expect(harnessRootSession("cycle", () => ({ parentID: "cycle" }))).toBeUndefined()
})

test("home does not query a previous session", async () => {
  const f = fixture()
  f.binding.select({ sessionID: "old" })
  f.binding.select(undefined)
  expect(await f.binding.refresh()).toBeUndefined()
  expect(f.requests).toHaveLength(0)
  expect(f.binding.accept({ sessionID: "old", phase: "ready" })).toBe(false)
})

for (const next of [{ sessionID: "other", directory: "/one" }, { sessionID: "root", directory: "/two" }]) {
  test("a late response cannot overwrite a changed session target: " + JSON.stringify(next), async () => {
    const f = fixture()
    f.binding.select({ sessionID: "root", directory: "/one" })
    const oldTarget = f.binding.current()
    const fetching = f.binding.refresh()
    f.binding.select(next)
    f.requests[0]!.result.resolve({ sessionID: "root", phase: "ready" })
    expect(await fetching).toBeUndefined()
    expect(f.published).toHaveLength(0)
    expect(f.binding.accept({ sessionID: "root", phase: "ready" }, oldTarget)).toBe(false)
  })
}

test("an unrelated session event does not select its run", () => {
  const f = fixture()
  f.binding.select({ sessionID: "root" })
  expect(f.binding.accept({ sessionID: "other", phase: "ready" })).toBe(false)
  expect(f.binding.current()?.sessionID).toBe("root")
  expect(f.published).toHaveLength(0)
})

test("a Host event supersedes an older in-flight status request", async () => {
  const f = fixture()
  f.binding.select({ sessionID: "root" })
  const fetching = f.binding.refresh()
  expect(f.binding.accept({ sessionID: "root", phase: "plan_ready" })).toBe(true)
  f.requests[0]!.result.resolve({ sessionID: "root", phase: "inactive" })
  expect(await fetching).toBeUndefined()
  expect(f.published.map((x) => x.phase)).toEqual(["plan_ready"])
})

test("the latest concurrent refresh wins", async () => {
  const f = fixture()
  f.binding.select({ sessionID: "root" })
  const first = f.binding.refresh()
  const second = f.binding.refresh()
  f.requests[1]!.result.resolve({ sessionID: "root", phase: "plan_ready" })
  await second
  f.requests[0]!.result.resolve({ sessionID: "root", phase: "inactive" })
  await first
  expect(f.published.map((x) => x.phase)).toEqual(["plan_ready"])
})

test("a mismatched Host response is rejected rather than displayed", async () => {
  const f = fixture()
  f.binding.select({ sessionID: "root" })
  const fetching = f.binding.refresh()
  f.requests[0]!.result.resolve({ sessionID: "other", phase: "ready" })
  await expect(fetching).rejects.toThrow("HARNESS_STATUS_SESSION_MISMATCH")
  expect(f.published).toHaveLength(0)
})

test("unmount invalidates pending requests and event callbacks", async () => {
  const f = fixture()
  f.binding.select({ sessionID: "root" })
  const fetching = f.binding.refresh()
  f.binding.dispose()
  f.requests[0]!.result.resolve({ sessionID: "root", phase: "ready" })
  expect(await fetching).toBeUndefined()
  expect(f.binding.accept({ sessionID: "root", phase: "ready" })).toBe(false)
  expect(f.published).toHaveLength(0)
})

const commands = [
  { display: "/plan", aliases: ["/plan-once"] },
  { display: "/plan discard" },
  { display: "/hackathon off" },
  { display: "/antigravity off" },
  { display: "/execute" },
  { display: "/harness" },
]

for (const input of ["/plan discard", "/hackathon off", "/antigravity off", "/execute", "/harness"]) {
  test("a registered control is matched before ordinary prompt dispatch: " + input, () => {
    expect(matchLocalSlash(input, commands)?.display).toBe(input)
  })
}

test("only exact registered syntax is a UI control, not natural language", () => {
  expect(matchLocalSlash(" /plan discard  ", commands)?.display).toBe("/plan discard")
  expect(matchLocalSlash("/plan-once", commands)?.display).toBe("/plan")
  for (const input of ["/plan discard extra", "/plan\ndiscard", "please /execute", "/unknown", "/plan build an app"]) {
    expect(matchLocalSlash(input, commands)).toBeUndefined()
  }
})
