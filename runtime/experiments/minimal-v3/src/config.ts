import { createHash } from "node:crypto"
import { homedir } from "node:os"
import { dirname, join, resolve } from "node:path"
import type { Risk } from "./types"

export interface ProviderConfig {
  type: string
  baseUrl?: string
  apiKey?: string
  apiKeyEnv?: string
  model?: string
  headers?: Record<string, string>
  request?: Record<string, unknown>
  capabilities?: { reasoningEfforts?: string[] }
}

export interface VerifierConfig {
  id: string
  command: string[]
  strength: "structural" | "execution" | "behavioral" | "external_oracle"
  claimKinds: Array<"artifact" | "execution" | "behavior" | "configuration" | "negative" | "external">
  methodId: string
  deterministicOracle?: boolean
  freshnessSeconds?: number
}

export type McpServerConfig = {
  enabled?: boolean
  command?: string
  args?: string[]
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string>
  include?: string[]
  exclude?: string[]
}

export interface HarnessConfig {
  provider: string
  model: string
  reasoningEffort?: string
  providers: Record<string, ProviderConfig>
  runtime: { maxIterations: number; maxRepairs: number; toolsets: string[] }
  verification: {
    profile: "fast" | "adaptive" | "strict"
    trigger: "auto" | "manual"
    maxSameFailureRepairs: number
    verifiers: VerifierConfig[]
    revokedVerifiers: string[]
  }
  mcp: Record<string, McpServerConfig>
  plugins: string[]
  skills: { paths: string[] }
}

export interface LoadedConfig {
  config: HarnessConfig
  files: string[]
  digest: string
}

const defaults: HarnessConfig = {
  provider: "local",
  model: "",
  providers: {
    local: { type: "openai-compatible", baseUrl: "http://127.0.0.1:11434/v1", apiKey: "ollama" },
  },
  runtime: { maxIterations: 32, maxRepairs: 2, toolsets: ["files", "shell", "subagent"] },
  verification: {
    profile: "adaptive",
    trigger: "auto",
    maxSameFailureRepairs: 2,
    verifiers: [],
    revokedVerifiers: [],
  },
  mcp: {},
  plugins: [],
  skills: { paths: [] },
}

function userConfigPath(): string {
  if (process.platform === "win32") return join(process.env.APPDATA ?? join(homedir(), "AppData", "Roaming"), "base-harness", "base-harness.jsonc")
  return join(process.env.XDG_CONFIG_HOME ?? join(homedir(), ".config"), "base-harness", "base-harness.jsonc")
}

function stripJsonc(text: string): string {
  let output = ""
  let string = false
  let escaped = false
  let lineComment = false
  let blockComment = false
  for (let index = 0; index < text.length; index++) {
    const current = text[index]
    const next = text[index + 1]
    if (lineComment) {
      if (current === "\n") { lineComment = false; output += current }
      continue
    }
    if (blockComment) {
      if (current === "*" && next === "/") { blockComment = false; index++ }
      else if (current === "\n") output += "\n"
      continue
    }
    if (string) {
      output += current
      if (escaped) escaped = false
      else if (current === "\\") escaped = true
      else if (current === '"') string = false
      continue
    }
    if (current === '"') { string = true; output += current; continue }
    if (current === "/" && next === "/") { lineComment = true; index++; continue }
    if (current === "/" && next === "*") { blockComment = true; index++; continue }
    output += current
  }
  return output.replace(/,\s*([}\]])/g, "$1")
}

function merge(left: unknown, right: unknown): unknown {
  if (!left || !right || typeof left !== "object" || typeof right !== "object" || Array.isArray(left) || Array.isArray(right)) return right
  const result: Record<string, unknown> = { ...(left as Record<string, unknown>) }
  for (const [key, value] of Object.entries(right as Record<string, unknown>)) result[key] = key in result ? merge(result[key], value) : value
  return result
}

export async function loadConfig(workspaceInput: string): Promise<LoadedConfig> {
  const workspace = resolve(workspaceInput)
  const paths = [userConfigPath(), join(workspace, "base-harness.jsonc")]
  let value: unknown = defaults
  const files: string[] = []
  for (const path of paths) {
    const file = Bun.file(path)
    if (!(await file.exists())) continue
    value = merge(value, JSON.parse(stripJsonc(await file.text())))
    files.push(path)
  }
  const config = value as HarnessConfig
  if (!config.providers?.[config.provider]) throw new Error(`Unknown provider profile: ${config.provider}`)
  config.model ||= config.providers[config.provider].model ?? ""
  if (!config.model) throw new Error("A model must be configured in base-harness.jsonc")
  if (!Array.isArray(config.runtime.toolsets)) throw new Error("runtime.toolsets must be an array")
  if (!Array.isArray(config.verification.verifiers)) throw new Error("verification.verifiers must be an array")
  config.plugins = (config.plugins ?? []).map((path) => resolve(dirname(files.at(-1) ?? join(workspace, "base-harness.jsonc")), path))
  config.skills.paths = (config.skills?.paths ?? []).map((path) => resolve(workspace, path))
  const digest = createHash("sha256").update(JSON.stringify(config)).digest("hex")
  return { config, files, digest }
}

export const riskRank = (risk: Risk): number => ({ low: 0, medium: 1, high: 2, critical: 3 })[risk]
