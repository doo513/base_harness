import { createHash } from "node:crypto"
import { constants as fsConstants, promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"
import {
  ANTIGRAVITY_ADAPTER_ID,
  ANTIGRAVITY_REASONING_OPTION,
  antigravityCommand,
  parseAntigravityCapabilities,
  parseAntigravityStreamEvent,
  type AntigravityCapabilities,
} from "@base-harness/core/antigravity-protocol"
import type { BackendMutationPolicy } from "./backend"

type ErrorCode =
  | "AGY_UNAVAILABLE"
  | "AGY_AUTH_REQUIRED"
  | "AGY_CAPABILITY_STALE"
  | "AGY_MODEL_UNAVAILABLE"
  | "AGY_OPTION_UNSUPPORTED"
  | "AGY_PROTOCOL_ERROR"
  | "AGY_RUN_FAILED"
  | "AGY_SCOPE_VIOLATION"
  | "AGY_DELETE_UNSUPPORTED"

export class AntigravityCliError extends Error {
  constructor(
    readonly code: ErrorCode,
    message: string,
    readonly details?: unknown,
  ) {
    const detailStr = details
      ? typeof details === "object"
        ? JSON.stringify(details)
        : String(details)
      : ""
    super(detailStr ? `${message}: ${detailStr}` : message)
    this.name = "AntigravityCliError"
  }
}

export interface ExecutionSelection {
  adapterID: string
  modelID?: string
  options?: Record<string, string>
  capabilityRevision?: string
}

interface SnapshotEntry {
  kind: "file" | "link"
  hash: string
  size: number
}

interface ManagedWorkspace {
  source: string
  root: string
  baseline: Map<string, SnapshotEntry>
  cleanup: ReturnType<typeof setTimeout>
}

interface ExecuteInput {
  sessionID: string
  workspace: string
  prompt: string
  modelID?: string
  options?: Record<string, string>
  capabilityRevision?: string
  phase?: string
  mutationPolicy?: BackendMutationPolicy
  signal?: AbortSignal
  routeWrite(relativePath: string): Promise<{ physicalPath: string }>
}

interface ExecuteResult {
  output: string
  changedFiles: string[]
  capabilityRevision: string
  resourceUsage?: { modelTokens: number; costMinorUnits: number }
}

// These directories are disposable execution state, not candidate artifacts.
// Apply the filter at every depth: a repository workspace commonly contains
// runtime/node_modules, package-level build output, and nested test caches.
// Walking those directories made the TUI appear hung before the first model
// request and could turn dependencies into an enormous candidate snapshot.
const excludedDirectories = new Set([
  ".git", ".venv", "venv", "Python", "node_modules", "dist", "build", ".next", "target",
  ".cache", ".pytest_cache", "__pycache__", ".tools", "coverage", ".turbo", ".vite",
])
const managed = new Map<string, ManagedWorkspace>()
const maxChangedFiles = 256
const maxChangedBytes = 50 * 1024 * 1024

function isExcludedPath(relative: string): boolean {
  return relative.split(path.sep).some((segment) => excludedDirectories.has(segment))
}

function childEnvironment(): Record<string, string> {
  const keys = [
    "PATH",
    "HOME",
    "USERPROFILE",
    "SystemRoot",
    "WINDIR",
    "TEMP",
    "TMP",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "TERM",
    "WSLENV",
  ]
  return Object.fromEntries(keys.flatMap((key) => (process.env[key] ? [[key, process.env[key]!]] : [])))
}

async function runCommand(command: string[], input?: string, signal?: AbortSignal, timeoutMs = 20_000, cwd?: string) {
  signal?.throwIfAborted()
  let processHandle: Bun.Subprocess<"pipe", "pipe", "pipe">
  try {
    processHandle = Bun.spawn(command, {
      stdin: "pipe",
      cwd,
      stdout: "pipe",
      stderr: "pipe",
      env: childEnvironment(),
    })
  } catch (error) {
    throw new AntigravityCliError("AGY_UNAVAILABLE", "The official Antigravity CLI could not be started", error)
  }

  const terminate = () => { try { processHandle.kill() } catch {} }
  signal?.addEventListener("abort", terminate, { once: true })
  const timeout = setTimeout(terminate, timeoutMs)
  try {
    if (input !== undefined) await processHandle.stdin.write(input)
    await processHandle.stdin.end()
    const [stdout, stderr, exitCode] = await Promise.all([
      new Response(processHandle.stdout).text(),
      new Response(processHandle.stderr).text(),
      processHandle.exited,
    ])
    return { stdout, stderr, exitCode }
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener("abort", terminate)
  }
}

function isInside(root: string, target: string): boolean {
  const relative = path.relative(root, target)
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative))
}

async function digestFile(file: string): Promise<string> {
  return createHash("sha256").update(await fs.readFile(file)).digest("hex")
}

async function snapshot(root: string, relative = "", result = new Map<string, SnapshotEntry>()) {
  const directory = path.join(root, relative)
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const childRelative = path.join(relative, entry.name)
    if (isExcludedPath(childRelative)) continue
    const child = path.join(root, childRelative)
    const stat = await fs.lstat(child)
    if (stat.isSymbolicLink()) {
      const resolved = await fs.realpath(child)
      if (!isInside(root, resolved)) {
        throw new AntigravityCliError("AGY_SCOPE_VIOLATION", `Link escapes the managed workspace: ${childRelative}`)
      }
      result.set(childRelative, {
        kind: "link",
        hash: createHash("sha256").update(await fs.readlink(child)).digest("hex"),
        size: 0,
      })
      continue
    }
    if (stat.isDirectory()) {
      await snapshot(root, childRelative, result)
      continue
    }
    if (!stat.isFile()) {
      throw new AntigravityCliError("AGY_SCOPE_VIOLATION", `Unsupported workspace entry: ${childRelative}`)
    }
    result.set(childRelative, { kind: "file", hash: await digestFile(child), size: stat.size })
  }
  return result
}

async function managedWorkspace(sessionID: string, workspace: string): Promise<ManagedWorkspace> {
  const source = await fs.realpath(workspace)
  const current = managed.get(sessionID)
  if (current && current.source === source) {
    clearTimeout(current.cleanup)
    current.cleanup = setTimeout(() => void dispose(sessionID), 60 * 60 * 1000)
    current.cleanup.unref?.()
    return current
  }
  if (current) await dispose(sessionID)
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "base-harness-agy-"))
  await snapshot(source)
  await fs.cp(source, root, {
    recursive: true,
    force: true,
    verbatimSymlinks: true,
    mode: fsConstants.COPYFILE_FICLONE,
    filter: (candidate) => {
      const relative = path.relative(source, candidate)
      if (!relative) return true
      return !isExcludedPath(relative)
    },
  })
  const record: ManagedWorkspace = {
    source,
    root,
    baseline: await snapshot(root),
    cleanup: setTimeout(() => void dispose(sessionID), 60 * 60 * 1000),
  }
  record.cleanup.unref?.()
  managed.set(sessionID, record)
  return record
}

async function dispose(sessionID: string): Promise<void> {
  const record = managed.get(sessionID)
  if (!record) return
  managed.delete(sessionID)
  clearTimeout(record.cleanup)
  await fs.rm(record.root, { recursive: true, force: true })
}

async function linuxPath(windowsPath: string): Promise<string> {
  // The native Windows backend must not depend on wsl.exe or wslpath.
  // antigravityCommand uses the same environment switch when choosing the
  // actual process backend.
  if (process.platform !== "win32" || process.env.BASE_HARNESS_AGY_USE_WSL === "0") return windowsPath
  const command = [
    "wsl.exe",
    ...(process.env.BASE_HARNESS_AGY_WSL_DISTRO ? ["-d", process.env.BASE_HARNESS_AGY_WSL_DISTRO] : []),
    "--",
    "wslpath",
    "-a",
    "-u",
    windowsPath,
  ]
  const result = await runCommand(command)
  if (result.exitCode !== 0 || !result.stdout.trim()) {
    throw new AntigravityCliError("AGY_UNAVAILABLE", "The managed workspace path could not be mapped into WSL")
  }
  return result.stdout.trim()
}

async function discover(): Promise<AntigravityCapabilities> {
  const options = { distro: process.env.BASE_HARNESS_AGY_WSL_DISTRO }
  const help = await runCommand(antigravityCommand(["--help"], options))
  const models = await runCommand(antigravityCommand(["models"], options))
  if (help.exitCode !== 0) {
    throw new AntigravityCliError("AGY_UNAVAILABLE", "The official Antigravity CLI did not return its capability contract")
  }
  const capabilities = parseAntigravityCapabilities(
    `${help.stdout}\n${help.stderr}`,
    `${models.stdout}\n${models.stderr}`,
  )
  if (models.exitCode !== 0 || capabilities.models.length === 0) {
    throw new AntigravityCliError("AGY_AUTH_REQUIRED", "Antigravity model capabilities are unavailable; authenticate with the official CLI first")
  }
  return {
    ...capabilities,
    revision: createHash("sha256").update(capabilities.revision).update("\0autonomous-decision-v1:reported-v1").digest("hex"),
  }
}

async function captureChanges(record: ManagedWorkspace, routeWrite: ExecuteInput["routeWrite"]): Promise<string[]> {
  const current = await snapshot(record.root)
  for (const relative of record.baseline.keys()) {
    if (!current.has(relative)) {
      throw new AntigravityCliError("AGY_DELETE_UNSUPPORTED", `Managed execution deleted a path: ${relative}`)
    }
  }
  const changed = [...current.entries()].filter(([relative, entry]) => record.baseline.get(relative)?.hash !== entry.hash)
  if (changed.length > maxChangedFiles || changed.reduce((total, [, entry]) => total + entry.size, 0) > maxChangedBytes) {
    throw new AntigravityCliError("AGY_SCOPE_VIOLATION", "Managed execution exceeded the candidate change limit")
  }
  const routes: Array<{ relative: string; sourcePath: string; physicalPath: string }> = []
  for (const [relative, entry] of changed) {
    if (entry.kind !== "file") {
      throw new AntigravityCliError("AGY_SCOPE_VIOLATION", `Managed execution changed a link: ${relative}`)
    }
    let route: { physicalPath: string }
    try {
      route = await routeWrite(relative.split(path.sep).join("/"))
    } catch (error) {
      throw new AntigravityCliError(
        "AGY_SCOPE_VIOLATION",
        `Managed execution could not publish ${relative}`,
        error,
      )
    }
    routes.push({ relative, sourcePath: path.join(record.root, relative), physicalPath: route.physicalPath })
  }
  // Resolve every destination before copying any file. A later scope failure
  // must not leave an earlier allowed file partially published.
  for (const route of routes) {
    await fs.mkdir(path.dirname(route.physicalPath), { recursive: true })
    await fs.copyFile(route.sourcePath, route.physicalPath)
  }
  return changed.map(([relative]) => relative.split(path.sep).join("/"))
}

export namespace AntigravityCli {
  export const id = ANTIGRAVITY_ADAPTER_ID

  export const capabilities = discover

  export function selectionFromEnvironment(): ExecutionSelection | undefined {
    if (process.env.BASE_HARNESS_EXECUTION_ADAPTER !== id) return undefined
    const effort = process.env.BASE_HARNESS_AGY_EFFORT
    return {
      adapterID: id,
      modelID: process.env.BASE_HARNESS_AGY_MODEL,
      options: effort ? { [ANTIGRAVITY_REASONING_OPTION]: effort } : undefined,
    }
  }

  export async function execute(input: ExecuteInput): Promise<ExecuteResult> {
    const capabilities = await discover()
    if (input.capabilityRevision && input.capabilityRevision !== capabilities.revision) {
      throw new AntigravityCliError("AGY_CAPABILITY_STALE", "Antigravity capabilities changed after selection")
    }
    if (input.modelID && !capabilities.models.includes(input.modelID)) {
      throw new AntigravityCliError("AGY_MODEL_UNAVAILABLE", `Selected Antigravity model is unavailable: ${input.modelID}`)
    }
    const options = input.options ?? {}
    const unknownOption = Object.keys(options).find((key) => key !== ANTIGRAVITY_REASONING_OPTION)
    if (unknownOption) {
      throw new AntigravityCliError("AGY_OPTION_UNSUPPORTED", `Unsupported Antigravity option: ${unknownOption}`)
    }
    const effort = options[ANTIGRAVITY_REASONING_OPTION]
    if (effort && !capabilities.reasoningEfforts.includes(effort)) {
      throw new AntigravityCliError("AGY_OPTION_UNSUPPORTED", `Unsupported Antigravity reasoning effort: ${effort}`)
    }

    const workspace = await managedWorkspace(input.sessionID, input.workspace)
    const mutationPolicy = input.mutationPolicy ?? (
      input.phase === "plan" || input.phase === "meta_review" ? "forbid" : "capture"
    )
    const executeManaged = async (): Promise<ExecuteResult> => {
    const useWsl = process.platform === "win32" && process.env.BASE_HARNESS_AGY_USE_WSL !== "0"
    const cwd = useWsl ? await linuxPath(workspace.root) : workspace.root
    const args = [
      "--input-format",
      "stream-json",
      "--output-format",
      "stream-json",
      "--disable-slash-commands",
      "--sandbox",
      ...(process.env.BASE_HARNESS_AGY_SKIP_PERMISSIONS === "0" ? [] : ["--dangerously-skip-permissions"]),
      "--mode",
      mutationPolicy === "forbid" ? "plan" : "accept-edits",
      "--add-dir",
      cwd,
      "--print-timeout",
      process.env.BASE_HARNESS_AGY_PRINT_TIMEOUT ?? "20m",
      ...(input.modelID ? ["--model", input.modelID] : []),
      ...(effort ? ["--effort", effort] : []),
    ]
    const command = antigravityCommand(args, {
      distro: process.env.BASE_HARNESS_AGY_WSL_DISTRO,
      linuxCwd: useWsl ? cwd : undefined,
    })
    const request = `${JSON.stringify({ event: "user", message: { content: input.prompt } })}\n`
    const result = await runCommand(command, request, input.signal, 25 * 60 * 1000, workspace.root)
    if (result.exitCode !== 0) {
      throw new AntigravityCliError("AGY_RUN_FAILED", "Antigravity managed execution failed", {
        exitCode: result.exitCode,
        stderr: result.stderr.slice(0, 4000),
        stdout: result.stdout.slice(0, 2000),
      })
    }

    let terminal: Record<string, unknown> | undefined
    try {
      for (const line of result.stdout.split(/\r?\n/).filter(Boolean)) {
        const event = parseAntigravityStreamEvent(line)
        if (event.event === "result") terminal = event
      }
    } catch (error) {
      throw new AntigravityCliError("AGY_PROTOCOL_ERROR", "Antigravity returned malformed stream-json", error)
    }
    const terminalPayload = terminal && isTerminalPayload(terminal.result) ? terminal.result : terminal
    const deniedActions = terminalPayload && Array.isArray((terminalPayload as { denied_actions?: unknown }).denied_actions)
      ? (terminalPayload as { denied_actions: unknown[] }).denied_actions
      : terminal && Array.isArray(terminal.denied_actions) ? terminal.denied_actions : []
    if (
      !terminalPayload || terminalPayload.status !== "SUCCESS" ||
      typeof terminalPayload.response !== "string" || !terminalPayload.response.trim() ||
      deniedActions.length > 0
    ) {
      throw new AntigravityCliError("AGY_RUN_FAILED", "Antigravity did not return a successful terminal result", terminal)
    }
    const usage = terminalPayload && typeof terminalPayload === "object" && !Array.isArray(terminalPayload)
      ? (terminalPayload as { usage?: unknown }).usage : undefined
    const usageRecord = usage && typeof usage === "object" && !Array.isArray(usage)
      ? usage as Record<string, unknown> : undefined
    const totalTokens = usageRecord?.total_tokens
    const resourceUsage = Number.isSafeInteger(totalTokens) && (totalTokens as number) >= 0
      ? { modelTokens: totalTokens as number, costMinorUnits: 0 }
      : undefined
    if (input.phase === "autonomous_decision" && !resourceUsage) {
      throw new AntigravityCliError("AGY_PROTOCOL_ERROR", "Antigravity autonomous execution did not report token usage")
    }
    if (mutationPolicy === "forbid") {
      return { output: terminalPayload.response, changedFiles: [], capabilityRevision: capabilities.revision,
        ...(resourceUsage ? { resourceUsage } : {}) }
    }
    const changedFiles = await captureChanges(workspace, input.routeWrite)
    return { output: terminalPayload.response, changedFiles, capabilityRevision: capabilities.revision,
      ...(resourceUsage ? { resourceUsage } : {}) }
    }
    return executeManaged().finally(async () => {
      if (mutationPolicy === "forbid") await dispose(input.sessionID)
    })
  }
}

function isTerminalPayload(value: unknown): value is { status: unknown; response: unknown } {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false
  const payload = value as Record<string, unknown>
  return "status" in payload || "response" in payload
}
