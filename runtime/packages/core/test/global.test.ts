import { describe, expect, test } from "bun:test"
import fs from "fs/promises"
import os from "os"
import path from "path"
import { Global } from "@base-harness/core/global"

describe("global paths", () => {
  test("tmp path is under the system temp directory", () => {
    expect(Global.Path.tmp).toBe(path.join(os.tmpdir(), "base-harness"))
    expect(Global.make().tmp).toBe(Global.Path.tmp)
  })

  test("tmp path is created on module load", async () => {
    expect((await fs.stat(Global.Path.tmp)).isDirectory()).toBe(true)
  })
})

test("Core writable global state is confined to its temporary test root", () => {
  const testHome = process.env.BASE_HARNESS_TEST_HOME
  expect(testHome).toBeDefined()
  const root = path.dirname(testHome!)
  expect(path.dirname(root)).toBe(path.resolve(os.tmpdir()))
  expect(path.basename(root).startsWith("base-harness-core-test-")).toBe(true)
  expect(process.env.LOCALAPPDATA).toBe(path.join(root, "local"))
  expect(process.env.APPDATA).toBe(path.join(root, "roaming"))
  for (const key of ["data", "cache", "config", "state"] as const) {
    const relative = path.relative(root, Global.Path[key])
    expect(relative.length).toBeGreaterThan(0)
    expect(path.isAbsolute(relative)).toBe(false)
    expect(relative === ".." || relative.startsWith(".." + path.sep)).toBe(false)
  }
})
