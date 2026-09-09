import { expect, test } from "bun:test"
import { mkdtemp, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { CandidateService } from "../src/candidate-service"

test("CandidateService contexts do not switch another instance's store", async () => {
  const directory = await mkdtemp(join(tmpdir(), "harness-store-boundary-"))
  const a = new CandidateService()
  const b = new CandidateService()
  try {
    a.api.beginPrompt({ sessionID: "same-session", workspace: directory, goal: "first", exploration: "manual" })
    b.api.beginPrompt({ sessionID: "same-session", workspace: directory, goal: "second", exploration: "manual" })
    a.api.registerContract("same-session", ["first-claim"], ["first-criterion"])
    expect(a.api.hasContract("same-session")).toBe(true)
    expect(b.api.hasContract("same-session")).toBe(false)
    await Bun.sleep(1)
    b.api.registerContract("same-session", ["second-claim"], ["second-criterion"])
    a.reset()
    expect(a.api.snapshot("same-session")).toBeUndefined()
    expect(b.api.hasContract("same-session")).toBe(true)
  } finally {
    a.reset()
    b.reset()
    await rm(directory, { recursive: true, force: true })
  }
})
