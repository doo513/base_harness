// IMPORTANT: Set env vars BEFORE any imports from src/ directory
// xdg-basedir reads env vars at import time, so we must set these first
import os from "os"
import path from "path"
import fs from "fs/promises"
import { setTimeout as sleep } from "node:timers/promises"
import { afterAll } from "bun:test"

// Set XDG env vars FIRST, before any src/ imports
const dir = path.join(os.tmpdir(), "opencode-test-data-" + process.pid)
await fs.mkdir(dir, { recursive: true })
afterAll(async () => {
  // Loading the full application just to dispose it makes pure tests pay for
  // provider, tool, and plugin imports. Only finalize a runtime already loaded.
  const { appRuntimeFinalizer } = await import("../src/effect/app-runtime-lifecycle")
  await appRuntimeFinalizer.dispose()

  const busy = (error: unknown) =>
    typeof error === "object" && error !== null && "code" in error && error.code === "EBUSY"
  const rm = async (left: number): Promise<void> => {
    Bun.gc(true)
    await sleep(100)
    return fs.rm(dir, { recursive: true, force: true }).catch((error) => {
      if (!busy(error)) throw error
      if (left <= 1 && process.platform !== "win32") throw error
      if (left <= 1) return
      return rm(left - 1)
    })
  }

  // Windows can keep SQLite WAL handles alive until GC finalizers run, so we
  // force GC and retry teardown to avoid flaky EBUSY in test cleanup.
  const resolved = path.resolve(dir)
  if (path.dirname(resolved) !== path.resolve(os.tmpdir())
      || path.basename(resolved) !== "opencode-test-data-" + process.pid) {
    throw new Error("Refusing test cleanup outside its process scratch directory")
  }
  await rm(30)
})

// Non-repository scratch directories must not inherit an ancestor checkout.
// This bounds Git discovery in tests; it is not a filesystem sandbox.
process.env.GIT_CEILING_DIRECTORIES = [
  process.env.GIT_CEILING_DIRECTORIES,
  await fs.realpath(os.tmpdir()),
].filter(Boolean).join(path.delimiter)

// Windows Global paths use LOCALAPPDATA, not XDG. Set both before application imports.
process.env["LOCALAPPDATA"] = path.join(dir, "local")
process.env["APPDATA"] = path.join(dir, "roaming")
for (const key of [
  "BASE_HARNESS_CONFIG", "BASE_HARNESS_CONFIG_DIR", "BASE_HARNESS_TUI_CONFIG",
  "BASE_HARNESS_CONFIG_CONTENT", "BASE_HARNESS_AUTH_CONTENT",
]) delete process.env[key]

process.env["XDG_DATA_HOME"] = path.join(dir, "share")
process.env["XDG_CACHE_HOME"] = path.join(dir, "cache")
process.env["XDG_CONFIG_HOME"] = path.join(dir, "config")
process.env["XDG_STATE_HOME"] = path.join(dir, "state")
process.env["BASE_HARNESS_MODELS_PATH"] = path.join(import.meta.dir, "tool", "fixtures", "models-api.json")
process.env["BASE_HARNESS_EXPERIMENTAL_EVENT_SYSTEM"] = "true"
process.env["BASE_HARNESS_EXPERIMENTAL_WORKSPACES"] = "true"

// Set test home directory to isolate tests from user's actual home directory
// This prevents tests from picking up real user configs/skills from ~/.claude/skills
const testHome = path.join(dir, "home")
await fs.mkdir(testHome, { recursive: true })
process.env["BASE_HARNESS_TEST_HOME"] = testHome

// Set test managed config directory to isolate tests from system managed settings
const testManagedConfigDir = path.join(dir, "managed")
process.env["BASE_HARNESS_TEST_MANAGED_CONFIG_DIR"] = testManagedConfigDir

// Write the cache version file to prevent global/index.ts from clearing the cache
const cacheDir = process.platform === "win32"
  ? path.join(dir, "local", "base-harness", "cache")
  : path.join(dir, "cache", "base-harness")
await fs.mkdir(cacheDir, { recursive: true })
await fs.writeFile(path.join(cacheDir, "version"), "14")

// Clear provider and server auth env vars to ensure clean test state
delete process.env["ANTHROPIC_API_KEY"]
delete process.env["OPENAI_API_KEY"]
delete process.env["GOOGLE_API_KEY"]
delete process.env["GOOGLE_GENERATIVE_AI_API_KEY"]
delete process.env["AZURE_OPENAI_API_KEY"]
delete process.env["AWS_ACCESS_KEY_ID"]
delete process.env["AWS_PROFILE"]
delete process.env["AWS_REGION"]
delete process.env["AWS_BEARER_TOKEN_BEDROCK"]
delete process.env["OPENROUTER_API_KEY"]
delete process.env["LLM_GATEWAY_API_KEY"]
delete process.env["GROQ_API_KEY"]
delete process.env["MISTRAL_API_KEY"]
delete process.env["PERPLEXITY_API_KEY"]
delete process.env["TOGETHER_API_KEY"]
delete process.env["XAI_API_KEY"]
delete process.env["DEEPSEEK_API_KEY"]
delete process.env["FIREWORKS_API_KEY"]
delete process.env["CEREBRAS_API_KEY"]
delete process.env["SAMBANOVA_API_KEY"]
delete process.env["BASE_HARNESS_SERVER_PASSWORD"]
delete process.env["BASE_HARNESS_SERVER_USERNAME"]
delete process.env["BASE_HARNESS_EXPERIMENTAL"]
delete process.env["BASE_HARNESS_ENABLE_EXPERIMENTAL_MODELS"]
delete process.env["OTEL_EXPORTER_OTLP_ENDPOINT"]
delete process.env["OTEL_EXPORTER_OTLP_HEADERS"]
delete process.env["OTEL_RESOURCE_ATTRIBUTES"]

// Use in-memory sqlite
process.env["BASE_HARNESS_DB"] = ":memory:"

// Fail before any test can write or clean a user's real configuration.
const { Global } = await import("@base-harness/core/global")
for (const key of ["data", "cache", "config", "state"] as const) {
  const relative = path.relative(dir, Global.Path[key])
  if (!relative || relative === ".." || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
    throw new Error("HOST_TEST_STATE_NOT_ISOLATED: " + key)
  }
}

// Now safe to import from src/
const { initProjectors } = await import("../src/server/projectors")

initProjectors()
