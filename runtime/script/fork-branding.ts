import { readFile, readdir, writeFile } from "node:fs/promises"
import path from "node:path"

const root = path.resolve(import.meta.dir, "../..")
let changed = 0

async function load(file: string) {
  return readFile(path.join(root, file), "utf8")
}

async function save(file: string, text: string) {
  const target = path.join(root, file)
  if ((await readFile(target, "utf8")) === text) return
  await writeFile(target, text)
  changed++
}

async function replace(file: string, pairs: Array<[string, string]>) {
  let text = await load(file)
  for (const [from, to] of pairs) text = text.replaceAll(from, to)
  await save(file, text)
}

const installation = `import { LayerNode } from "@base-harness/core/effect/layer-node"
import { AppNodeBuilder } from "@base-harness/core/effect/app-node-builder"
import { Effect, Layer, Schema, Context } from "effect"
import { serviceUse } from "@base-harness/core/effect/service-use"
import { makeRuntime } from "@base-harness/core/effect/runtime"
import semver from "semver"
import { InstallationChannel, InstallationVersion } from "@base-harness/core/installation/version"
import { InstallationEvent } from "@base-harness/schema/installation-event"

export type Method = "curl" | "npm" | "yarn" | "pnpm" | "bun" | "brew" | "scoop" | "choco" | "unknown"
export type ReleaseType = "patch" | "minor" | "major"

export const Event = InstallationEvent

export function getReleaseType(current: string, latest: string): ReleaseType {
  const currMajor = semver.major(current)
  const currMinor = semver.minor(current)
  const newMajor = semver.major(latest)
  const newMinor = semver.minor(latest)
  if (newMajor > currMajor) return "major"
  if (newMinor > currMinor) return "minor"
  return "patch"
}

export const Info = Schema.Struct({
  version: Schema.String,
  latest: Schema.String,
}).annotate({ identifier: "InstallationInfo" })
export type Info = Schema.Schema.Type<typeof Info>

export function userAgent(client = "cli") {
  return \`base-harness/\${InstallationChannel}/\${InstallationVersion}/\${client}\`
}

export const USER_AGENT = userAgent()

export function isPreview() {
  return InstallationChannel !== "latest"
}

export function isLocal() {
  return InstallationChannel === "local"
}

export class UpgradeFailedError extends Schema.TaggedErrorClass<UpgradeFailedError>()("UpgradeFailedError", {
  stderr: Schema.String,
}) {
  override get message() {
    return this.stderr
  }
}

export interface Interface {
  readonly info: () => Effect.Effect<Info>
  readonly method: () => Effect.Effect<Method>
  readonly latest: (method?: Method) => Effect.Effect<string>
  readonly upgrade: (method: Method, target: string) => Effect.Effect<void, UpgradeFailedError>
}

export class Service extends Context.Service<Service, Interface>()("@base-harness/Installation") {}
export const use = serviceUse(Service)

const unavailable = "Automatic updates are not available in the independent base-harness distribution."
const service = Service.of({
  info: () => Effect.succeed({ version: InstallationVersion, latest: InstallationVersion }),
  method: () => Effect.succeed("unknown" as Method),
  latest: () => Effect.succeed(InstallationVersion),
  upgrade: () => Effect.fail(new UpgradeFailedError({ stderr: unavailable })),
})
const layer = Layer.succeed(Service, service)

export const node = LayerNode.make({ service: Service, layer, deps: [] })

const { runPromise } = makeRuntime(Service, AppNodeBuilder.build(node))
export const latest = (...args: Parameters<Interface["latest"]>) => runPromise((s) => s.latest(...args))
export const method = () => runPromise((s) => s.method())
export const upgrade = (...args: Parameters<Interface["upgrade"]>) => runPromise((s) => s.upgrade(...args))

export * as Installation from "."
`
await save("runtime/packages/base-harness/src/installation/index.ts", installation)

const cliFiles = [
  "runtime/packages/base-harness/src/cli/network.ts",
  "runtime/packages/base-harness/src/cli/cmd/attach.ts",
  "runtime/packages/base-harness/src/cli/cmd/mcp.ts",
  "runtime/packages/base-harness/src/cli/cmd/web.ts",
  "runtime/packages/base-harness/src/cli/cmd/tui.ts",
  "runtime/packages/base-harness/src/cli/cmd/serve.ts",
  "runtime/packages/base-harness/src/cli/cmd/run.ts",
  "runtime/packages/base-harness/src/cli/cmd/debug/index.ts",
]
for (const file of cliFiles) {
  const text = (await load(file))
    .replaceAll("opencode", "base-harness")
    .replace(
      "e.g., base-harness x @modelcontextprotocol/server-filesystem",
      "e.g., npx -y @modelcontextprotocol/server-filesystem",
    )
  await save(file, text)
}

await replace("runtime/packages/base-harness/src/cli/error.ts", [
  [
    'return `MCP server "${data}" failed. Note, opencode does not support MCP authentication yet.`',
    'return `MCP server "${data}" failed.`',
  ],
  ["opencode models", "base-harness models"],
  ["opencode auth login", "base-harness auth login"],
])
await replace("runtime/packages/base-harness/src/mcp/index.ts", [
  ["Run: opencode mcp auth", "Run: base-harness mcp auth"],
])
await replace("runtime/packages/base-harness/src/provider/error.ts", [
  ["opencode auth login", "base-harness auth login"],
])
await replace("runtime/packages/base-harness/src/provider/provider.ts", [
  ["opencode auth cloudflare-ai-gateway", "base-harness auth cloudflare-ai-gateway"],
  ["via env var, opencode auth, or provider options", "via env var, base-harness auth, or provider options"],
])
await replace("runtime/packages/base-harness/src/cli/cmd/providers.ts", [
  ['describe: "opencode auth provider"', 'describe: "base-harness auth provider"'],
])
await replace("runtime/packages/base-harness/src/worktree/index.ts", [
  ["`opencode/${name}`", "`base-harness/${name}`"],
])
await replace("runtime/packages/base-harness/src/lsp/server.ts", [
  ['"opencode-jdtls-data"', '"base-harness-jdtls-data"'],
])
await replace("runtime/packages/core/src/project.ts", [
  ['path.join(dir, "opencode")', 'path.join(dir, "base-harness")'],
  ['path.join(input.store, "opencode")', 'path.join(input.store, "base-harness")'],
])
await replace("runtime/packages/core/src/database/database.ts", [
  ['"opencode.db"', '"base-harness.db"'],
  [
    '`opencode-${InstallationChannel.replace(/[^a-zA-Z0-9._-]/g, "-")}.db`',
    '`base-harness-${InstallationChannel.replace(/[^a-zA-Z0-9._-]/g, "-")}.db`',
  ],
])
await replace("runtime/packages/base-harness/test/fixture/fixture.ts", [
  ['"opencode-test-"', '"base-harness-test-"'],
  ['"test@opencode.test"', '"test@base-harness.test"'],
])

for (const file of [
  "runtime/packages/base-harness/src/session/prompt/default.txt",
  "runtime/packages/base-harness/src/session/prompt/gemini.txt",
  "runtime/packages/base-harness/src/session/prompt/beast.txt",
  "runtime/packages/base-harness/src/session/prompt/trinity.txt",
]) {
  await replace(file, [["You are opencode", "You are base-harness"]])
}

for (const file of [
  "runtime/packages/tui/src/keymap.tsx",
  "runtime/packages/tui/src/app.tsx",
  "runtime/packages/tui/src/config/keybind.ts",
  "runtime/packages/tui/src/prompt/traits.ts",
  "runtime/packages/tui/src/util/presentation.ts",
  "runtime/packages/tui/src/component/dialog-status.tsx",
  "runtime/packages/tui/src/clipboard.ts",
  "runtime/packages/tui/src/feature-plugins/system/diff-viewer.tsx",
]) {
  await save(file, (await load(file)).replaceAll("opencode", "base-harness"))
}

await replace("runtime/packages/tui/src/util/error.ts", [
  ["Try: `opencode models`", "Try: `base-harness models`"],
  [
    'return `MCP server "${name}" failed. Note, opencode does not support MCP authentication yet.`',
    'return `MCP server "${name}" failed.`',
  ],
])
let tips = await load("runtime/packages/tui/src/feature-plugins/home/tips-view.tsx")
tips = tips
  .split(/\r?\n/)
  .filter(
    (line) =>
      !["opencode upgrade", "/opencode", "opencode github", "docker run -it"].some((value) =>
        line.includes(value),
      ),
  )
  .join("\n")
  .replaceAll("opencode", "base-harness")
  .replace("~/.config/base-harness/tui.json", "~/.config/base-harness/base-harness.jsonc")
await save("runtime/packages/tui/src/feature-plugins/home/tips-view.tsx", tips)

let crash = await load("runtime/packages/tui/src/component/error-component.tsx")
crash = crash
  .replace(
    "https://github.com/anomalyco/opencode/issues/new?template=bug-report.yml",
    "https://github.com/doo513/base_harness/issues/new",
  )
  .replaceAll("opencode", "base-harness")
await save("runtime/packages/tui/src/component/error-component.tsx", crash)

await replace("runtime/packages/tui/src/theme/index.ts", [
  [
    'import opencode from "./assets/base-harness.json" with { type: "json" }',
    'import baseHarness from "./assets/base-harness.json" with { type: "json" }',
  ],
  ["  opencode,", '  "base-harness": baseHarness,'],
])
let theme = await load("runtime/packages/tui/src/context/theme.tsx")
theme = theme
  .replaceAll('"opencode"', '"base-harness"')
  .replaceAll("store.themes.opencode", 'store.themes["base-harness"]')
await save("runtime/packages/tui/src/context/theme.tsx", theme)

for (const file of [
  "runtime/packages/base-harness/src/session/prompt/default.txt",
  "runtime/packages/base-harness/src/session/prompt/anthropic.txt",
  "runtime/packages/base-harness/src/session/prompt/meta.txt",
  "runtime/packages/base-harness/src/session/prompt/copilot-gpt-5.txt",
]) {
  const text = (await load(file))
    .replaceAll("https://github.com/anomalyco/opencode", "https://github.com/doo513/base_harness")
    .replaceAll("https://base-harness.local/docs", "https://github.com/doo513/base_harness")
    .replaceAll("https://base-harness.local", "https://github.com/doo513/base_harness")
    .replaceAll("opencode", "base-harness")
  await save(file, text)
}

await replace("runtime/packages/base-harness/src/plugin/install.ts", [
  ['"opencode" | "tui"', '"base-harness" | "tui"'],
  ['return "opencode"', 'return "base-harness"'],
])
await replace("runtime/packages/base-harness/src/cli/cmd/plug.ts", [
  ['"opencode" | "tui"', '"base-harness" | "tui"'],
])
await replace("runtime/packages/base-harness/src/plugin/shared.ts", [
  ["opencodeVersion", "baseHarnessVersion"],
  ["engines.opencode", 'engines["base-harness"]'],
  ["Plugin requires opencode", "Plugin requires base-harness"],
])
await replace("runtime/packages/base-harness/src/plugin/xai.ts", [["referrer: \"opencode\"", 'referrer: "base-harness"']])
await replace("runtime/packages/tui/src/config/index.tsx", [["opencode.default", "base-harness.default"]])
for (const file of [
  "runtime/packages/sdk/js/src/error-interceptor.ts",
  "runtime/packages/sdk/js/src/server.ts",
  "runtime/packages/sdk/js/src/v2/server.ts",
]) {
  await save(file, (await load(file)).replaceAll("opencode server", "base-harness server"))
}

async function walk(dir: string): Promise<string[]> {
  const out: string[] = []
  for (const item of await readdir(dir, { withFileTypes: true })) {
    const next = path.join(dir, item.name)
    if (item.isDirectory()) out.push(...(await walk(next)))
    else if (/\.(ts|tsx)$/.test(item.name)) out.push(next)
  }
  return out
}
for (const dir of [
  "runtime/packages/base-harness/src",
  "runtime/packages/core/src",
  "runtime/packages/tui/src",
  "runtime/packages/sdk/js/src",
  "runtime/packages/plugin/src",
  "runtime/packages/base-harness/test",
]) {
  for (const file of await walk(path.join(root, dir))) {
    const text = await readFile(file, "utf8")
    const next = text
      .replaceAll("opencode/${Installation", "base-harness/${Installation")
      .replaceAll("x-opencode-directory", "x-base-harness-directory")
      .replaceAll("x-opencode-workspace", "x-base-harness-workspace")
      .replaceAll("x-opencode-sync", "x-base-harness-sync")
      .replaceAll("x-opencode-ticket", "x-base-harness-ticket")
    if (next !== text) {
      await writeFile(file, next)
      changed++
    }
  }
}

process.stdout.write(`fork branding updated ${changed} files\n`)
