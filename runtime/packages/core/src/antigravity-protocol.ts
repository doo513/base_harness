import { createHash } from "node:crypto"

export const ANTIGRAVITY_ADAPTER_ID = "antigravity-cli"
export const ANTIGRAVITY_REASONING_OPTION = "reasoning_effort"

export interface AntigravityCapabilities {
  adapterID: typeof ANTIGRAVITY_ADAPTER_ID
  revision: string
  models: string[]
  reasoningEfforts: string[]
}

export interface AntigravityCommandOptions {
  distro?: string
  linuxCwd?: string
}

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`
}

export function antigravityCommand(args: string[], options: AntigravityCommandOptions = {}): string[] {
  if (process.platform !== "win32") return ["agy", ...args]
  const command = ["exec", "agy", ...args].map(shellQuote).join(" ")
  return [
    "wsl.exe",
    ...(options.distro ? ["-d", options.distro] : []),
    ...(options.linuxCwd ? ["--cd", options.linuxCwd] : []),
    "--",
    "/bin/sh",
    "-lc",
    command,
  ]
}

function parseReasoningEfforts(help: string): string[] {
  for (const line of help.split(/\r?\n/)) {
    if (!line.includes("--effort")) continue
    const group = line.match(/\(([^)]+)\)/)?.[1]
    if (!group) continue
    return [...new Set(group.split("|").map((value) => value.trim()).filter((value) => /^[a-z0-9._-]+$/i.test(value)))]
  }
  return []
}

function parseModels(output: string): string[] {
  const models = new Set<string>()
  for (const raw of output.split(/\s+/)) {
    const token = raw.replace(/^[^a-z0-9]+|[^a-z0-9._/-]+$/gi, "")
    if (!/^[a-z0-9][a-z0-9._/-]*$/i.test(token)) continue
    if (!/\d/.test(token)) continue
    if ((token.match(/-/g)?.length ?? 0) < 2) continue
    models.add(token)
  }
  return [...models].sort()
}

export function parseAntigravityCapabilities(help: string, models: string): AntigravityCapabilities {
  const revision = createHash("sha256").update(help).update("\0").update(models).digest("hex")
  return {
    adapterID: ANTIGRAVITY_ADAPTER_ID,
    revision,
    models: parseModels(models),
    reasoningEfforts: parseReasoningEfforts(help),
  }
}

export interface AntigravityStreamEvent {
  event: string
  [key: string]: unknown
}

export function parseAntigravityStreamEvent(line: string): AntigravityStreamEvent {
  const value: unknown = JSON.parse(line)
  if (!value || typeof value !== "object" || typeof (value as { event?: unknown }).event !== "string") {
    throw new Error("Antigravity stream event is not a typed object")
  }
  return value as AntigravityStreamEvent
}
