import { tool } from "@base-harness/plugin"
import * as tui from "@base-harness/plugin/tui"
import { define as defineEffect } from "@base-harness/plugin/v2/effect"
import { define as defineEffectPlugin } from "@base-harness/plugin/v2/effect/plugin"
import { define as definePromise } from "@base-harness/plugin/v2/promise"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"

const MODULES = Symbol.for("base-harness.builtin-plugin.modules")
const REGISTERED = Symbol.for("base-harness.builtin-plugin.registered")

const modules = {
  "@base-harness/plugin": { tool },
  "@base-harness/plugin/tool": { tool },
  "@base-harness/plugin/tui": tui,
  "@base-harness/plugin/v2/effect": { define: defineEffect },
  "@base-harness/plugin/v2/effect/integration": {},
  "@base-harness/plugin/v2/effect/plugin": { define: defineEffectPlugin },
  "@base-harness/plugin/v2/promise": { define: definePromise },
} as const

type ModuleName = keyof typeof modules
type RuntimeGlobal = typeof globalThis & Record<symbol, unknown>

function source(name: ModuleName) {
  const exports = Object.keys(modules[name])
  const prefix = [
    `const modules = globalThis[Symbol.for(${JSON.stringify(Symbol.keyFor(MODULES))})]`,
    `const value = modules[${JSON.stringify(name)}]`,
  ]
  return [...prefix, ...exports.map((item) => `export const ${item} = value[${JSON.stringify(item)}]`)].join("\n")
}

export function registerBuiltinPluginModule() {
  const runtime = globalThis as RuntimeGlobal
  runtime[MODULES] = modules
  if (runtime[REGISTERED]) return
  runtime[REGISTERED] = true
}

export async function provisionBuiltinPluginModule(directory: string) {
  const root = path.join(directory, "node_modules", "@base-harness", "plugin")
  const dist = path.join(root, "dist")
  const files: Record<string, ModuleName> = {
    "index.js": "@base-harness/plugin",
    "tool.js": "@base-harness/plugin/tool",
    "tui.js": "@base-harness/plugin/tui",
    "v2-effect.js": "@base-harness/plugin/v2/effect",
    "v2-effect-integration.js": "@base-harness/plugin/v2/effect/integration",
    "v2-effect-plugin.js": "@base-harness/plugin/v2/effect/plugin",
    "v2-promise.js": "@base-harness/plugin/v2/promise",
  }
  const manifest = {
    name: "@base-harness/plugin",
    version: "0.1.0",
    private: true,
    type: "module",
    exports: {
      ".": "./dist/index.js",
      "./tool": "./dist/tool.js",
      "./tui": "./dist/tui.js",
      "./v2/effect": "./dist/v2-effect.js",
      "./v2/effect/integration": "./dist/v2-effect-integration.js",
      "./v2/effect/plugin": "./dist/v2-effect-plugin.js",
      "./v2/promise": "./dist/v2-promise.js",
    },
  }

  await mkdir(dist, { recursive: true })
  await Promise.all([
    writeFile(path.join(root, "package.json"), JSON.stringify(manifest, null, 2) + "\n"),
    ...Object.entries(files).map(([file, name]) => writeFile(path.join(dist, file), source(name) + "\n")),
  ])
}

registerBuiltinPluginModule()
