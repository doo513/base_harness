import path from "path"
import os from "node:os"
import { realpathSync } from "node:fs"
import fs from "node:fs/promises"
import { afterAll } from "bun:test"

const tempRoot = path.resolve(os.tmpdir())
const stateRoot = await fs.mkdtemp(path.join(tempRoot, "base-harness-core-test-"))

// Global resolves Windows LOCALAPPDATA and Linux XDG paths at import time.
process.env.LOCALAPPDATA = path.join(stateRoot, "local")
process.env.APPDATA = path.join(stateRoot, "roaming")
process.env.XDG_DATA_HOME = path.join(stateRoot, "share")
process.env.XDG_CACHE_HOME = path.join(stateRoot, "cache")
process.env.XDG_CONFIG_HOME = path.join(stateRoot, "config")
process.env.XDG_STATE_HOME = path.join(stateRoot, "state")
process.env.BASE_HARNESS_TEST_HOME = path.join(stateRoot, "home")
process.env.BASE_HARNESS_TEST_MANAGED_CONFIG_DIR = path.join(stateRoot, "managed")
await fs.mkdir(process.env.BASE_HARNESS_TEST_HOME, { recursive: true })
for (const key of [
  "BASE_HARNESS_CONFIG", "BASE_HARNESS_CONFIG_DIR", "BASE_HARNESS_TUI_CONFIG",
  "BASE_HARNESS_CONFIG_CONTENT", "BASE_HARNESS_AUTH_CONTENT",
]) delete process.env[key]

process.env.BASE_HARNESS_DB = ":memory:"
process.env.BASE_HARNESS_MODELS_PATH = path.join(import.meta.dir, "plugin", "fixtures", "models-dev.json")
process.env.BASE_HARNESS_DISABLE_MODELS_FETCH = "true"

// Scratch repositories must not inherit a developer's ancestor checkout.
// Preserve any existing ceilings; this environment belongs to the test process.
process.env.GIT_CEILING_DIRECTORIES = [
  process.env.GIT_CEILING_DIRECTORIES,
  realpathSync(os.tmpdir()),
].filter(Boolean).join(path.delimiter)

afterAll(async () => {
  const resolved = path.resolve(stateRoot)
  if (path.dirname(resolved) !== tempRoot || !path.basename(resolved).startsWith("base-harness-core-test-")) {
    throw new Error("Refusing Core test cleanup outside its scratch directory")
  }
  Bun.gc(true)
  await fs.rm(resolved, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }).catch((error: unknown) => {
    if (process.platform === "win32" && typeof error === "object" && error !== null
        && "code" in error && error.code === "EBUSY") {
      console.warn("Core test scratch retained because Windows still holds an open handle: " + resolved)
      return
    }
    throw error
  })
})

// Reject a preloaded or misconfigured Global before tests can mutate real state.
const { Global } = await import("../src/global")
for (const key of ["data", "cache", "config", "state"] as const) {
  const relative = path.relative(stateRoot, Global.Path[key])
  if (!relative || relative === ".." || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
    throw new Error("CORE_TEST_STATE_NOT_ISOLATED: " + key)
  }
}
