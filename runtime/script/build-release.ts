import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs"
import { basename, join, resolve } from "node:path"

const runtime = resolve(import.meta.dir, "..")
const product = await Bun.file(join(runtime, "package.json")).json()
const version = typeof product.version === "string" ? product.version : "0.1.0"
const targetName = process.argv[2] ?? (process.platform === "win32" ? "windows-x64" : "linux-x64")
const targets: Record<string, { bun: string; executable: string }> = {
  "windows-x64": {
    bun: "bun-windows-x64",
    executable: "base-harness.exe",
  },
  "linux-x64": {
    bun: "bun-linux-x64",
    executable: "base-harness",
  },
}
const target = targets[targetName]
if (!target) throw new Error("Unsupported release target: " + targetName)

const output = join(runtime, "dist", targetName)
if (existsSync(output)) rmSync(output, { recursive: true })
mkdirSync(output, { recursive: true })

const build = Bun.spawnSync([
  process.execPath,
  "build",
  "--compile",
  "--target=" + target.bun,
  "--define=BASE_HARNESS_VERSION=" + JSON.stringify(version),
  "--define=BASE_HARNESS_CHANNEL=" + JSON.stringify("stable"),
  "--outfile=" + join(output, target.executable),
  join(runtime, "packages", "base-harness", "src", "index.ts"),
], {
  cwd: runtime,
  stdout: "inherit",
  stderr: "inherit",
})
if (build.exitCode !== 0) throw new Error("Bun executable build failed")

for (const path of [
  join(runtime, "base-harness.schema.json"),
  join(runtime, "LICENSE"),
  join(runtime, "UPSTREAM_NOTICE.md"),
]) {
  cpSync(path, join(output, basename(path)))
}

process.stdout.write("Built " + targetName + " execution core at " + output + "\n")
