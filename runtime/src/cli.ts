#!/usr/bin/env bun
import { existsSync } from "node:fs"
import { resolve } from "node:path"

// This launcher has no model, tool, verification, or completion authority.
const repository = resolve(import.meta.dir, "../..")
const localBun = resolve(repository, ".tools", "bun-1.3.14", process.platform === "win32" ? "bun.exe" : "bun")
const python = resolve(repository, ".tools", "verifier", process.platform === "win32" ? "Scripts/python.exe" : "bin/python")
const executable = existsSync(localBun) ? localBun : process.execPath
const environment = { ...process.env }
const hostDirectory = resolve(import.meta.dir, "../packages/base-harness")
environment.BASE_HARNESS_LAUNCH_CWD ??= process.cwd()
environment.BASE_HARNESS_DISABLE_AUTOUPDATE ??= "1"
if (!environment.BASE_HARNESS_PYTHON && existsSync(python)) environment.BASE_HARNESS_PYTHON = python

const host = Bun.spawn([
  executable, "run", "--conditions=browser",
  resolve(hostDirectory, "src/source-launcher.ts"),
  ...process.argv.slice(2),
], {
  cwd: hostDirectory,
  env: environment,
  stdin: "inherit",
  stdout: "inherit",
  stderr: "inherit",
})
const interrupt = () => { try { host.kill("SIGINT") } catch {} }
const terminate = () => { try { host.kill("SIGTERM") } catch {} }
process.once("SIGINT", interrupt)
process.once("SIGTERM", terminate)
let exitCode = 1
try {
  exitCode = await host.exited
} finally {
  process.off("SIGINT", interrupt)
  process.off("SIGTERM", terminate)
}
process.exit(exitCode)
