import { expect, test } from "bun:test"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import * as PublicApi from "../src"
import { RunRepository } from "../src/run-repository"

test("Coordinator public runtime API is intentionally small", () => {
  expect(Object.keys(PublicApi).sort()).toEqual([
    "CandidateService",
    "Coordinator",
    "CoordinatorRuntime",
    "RunRepository",
  ])
})

test("unfinished persisted runs recover as interrupted instead of resuming", async () => {
  const stateDirectory = await mkdtemp(join(tmpdir(), "base-harness-run-repository-"))
  try {
    const target = join(stateDirectory, "run-stale.json")
    await writeFile(
      target,
      JSON.stringify({
        schemaVersion: "coordinator-run-v1",
        sessionID: "stale",
        runId: "run-stale",
        workspace: "workspace",
        phase: "worker_running",
        interrupted: false,
      }),
      "utf8",
    )
    const repository = new RunRepository({ stateDirectory })
    await repository.initialize()

    const recovered = JSON.parse(await readFile(target, "utf8"))
    expect(recovered.phase).toBe("interrupted")
    expect(recovered.interrupted).toBe(true)
  } finally {
    await rm(stateDirectory, { recursive: true, force: true })
  }
})
