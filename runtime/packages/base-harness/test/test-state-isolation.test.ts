import { expect, test } from "bun:test"
import path from "node:path"
import os from "node:os"
import { realpath } from "node:fs/promises"
import { Global } from "@base-harness/core/global"

test("Host writable global paths stay in process-owned test state", () => {
  const root = path.join(os.tmpdir(), "opencode-test-data-" + process.pid)
  for (const key of ["data", "cache", "config", "state"] as const) {
    const relative = path.relative(root, Global.Path[key])
    expect(relative.length).toBeGreaterThan(0)
    expect(path.isAbsolute(relative)).toBe(false)
    expect(relative === ".." || relative.startsWith(".." + path.sep)).toBe(false)
  }
  expect(process.env.LOCALAPPDATA).toBe(path.join(root, "local"))
  expect(process.env.APPDATA).toBe(path.join(root, "roaming"))
})

test("Host Git discovery stops at the canonical temporary root", async () => {
  expect(process.env.GIT_CEILING_DIRECTORIES?.split(path.delimiter)).toContain(await realpath(os.tmpdir()))
})
