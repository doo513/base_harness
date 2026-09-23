import { createHash } from "node:crypto"
import { createManagedWorkspace } from "./managed-workspace"
import {
  BackendExecutionError,
  type BackendCapabilities,
  type BackendExecutionInput,
  type BackendExecutionResult,
  type ExecutionBackend,
} from "./backend"

type JsonObject = Record<string, unknown>

const id = "codex-app-server"
const defaultCodexBinary = () => process.env.BASE_HARNESS_CODEX_APP_SERVER_PATH?.trim() || "codex"
const command = () => process.env.BASE_HARNESS_CODEX_BINARY ?? defaultCodexBinary()
const timeoutMs = 25 * 60 * 1000

function record(value: unknown): JsonObject | undefined {
  return value && typeof value === "object" ? value as JsonObject : undefined
}

function errorText(value: unknown) {
  const item = record(value)
  return typeof item?.message === "string" ? item.message : String(value)
}

function reportedTokens(value: unknown, depth = 0): number | undefined {
  if (depth > 6 || !value || typeof value !== "object") return
  if (Array.isArray(value)) {
    const totals = value.flatMap((item) => {
      const total = reportedTokens(item, depth + 1)
      return total === undefined ? [] : [total]
    })
    return totals.length ? Math.max(...totals) : undefined
  }
  const item = value as Record<string, unknown>
  for (const key of ["total_tokens", "totalTokens", "totalTokenCount"]) {
    const total = item[key]
    if (Number.isSafeInteger(total) && (total as number) >= 0) return total as number
  }
  const parts = ["input_tokens", "inputTokens", "output_tokens", "outputTokens",
    "reasoning_tokens", "reasoningTokens", "cached_input_tokens", "cachedInputTokens"]
    .map((key) => item[key]).filter((part): part is number => Number.isSafeInteger(part) && (part as number) >= 0)
  if (parts.length) return parts.reduce((sum, part) => sum + part, 0)
  const nested = Object.values(item).flatMap((child) => {
    const total = reportedTokens(child, depth + 1)
    return total === undefined ? [] : [total]
  })
  return nested.length ? Math.max(...nested) : undefined
}

function modelsFrom(result: JsonObject) {
  const payload = record(result.result) ?? {}
  const values = Array.isArray(payload.models)
    ? payload.models
    : Array.isArray(payload.data)
      ? payload.data
      : Array.isArray(payload.items)
        ? payload.items
      : []
  return values.flatMap((value) => {
    const item = record(value)
    const modelId = typeof item?.id === "string" ? item.id : typeof item?.modelId === "string" ? item.modelId : undefined
    if (!modelId) return []
    const efforts = Array.isArray(item?.supportedReasoningEfforts)
      ? item.supportedReasoningEfforts.flatMap((effort) => {
          const value = record(effort)
          return typeof value?.reasoningEffort === "string" ? [value.reasoningEffort] : typeof effort === "string" ? [effort] : []
        })
      : []
    return [{
      modelId,
      reasoningEfforts: efforts,
      defaultReasoningEffort: typeof item?.defaultReasoningEffort === "string" ? item.defaultReasoningEffort : undefined,
    }]
  })
}

function processEnv() {
  const env: Record<string, string> = {}
  for (const key of ["PATH", "HOME", "USERPROFILE", "SystemRoot", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "TERM"]) {
    const value = process.env[key]
    if (value !== undefined) env[key] = value
  }
  return env
}

function lineReader(stream: ReadableStream<Uint8Array>) {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  return {
    async next(): Promise<JsonObject | undefined> {
      while (true) {
        const newline = buffer.indexOf("\n")
        if (newline >= 0) {
          const line = buffer.slice(0, newline).trim()
          buffer = buffer.slice(newline + 1)
          if (!line) continue
          try {
            const value = JSON.parse(line)
            return record(value)
          } catch {
            throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Codex app-server returned malformed JSONL", line)
          }
        }
        const part = await reader.read()
        if (part.done) {
          const line = buffer.trim()
          buffer = ""
          if (!line) return
          try {
            return record(JSON.parse(line))
          } catch {
            throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Codex app-server returned malformed JSONL", line)
          }
        }
        buffer += decoder.decode(part.value, { stream: true })
      }
    },
    cancel() {
      return reader.cancel()
    },
  }
}

async function start() {
  try {
    return Bun.spawn([command(), "app-server"], {
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
      env: processEnv(),
    })
  } catch (error) {
    throw new BackendExecutionError("BACKEND_UNAVAILABLE", "Codex app-server could not be started", error)
  }
}

async function write(processHandle: ReturnType<typeof Bun.spawn>, value: JsonObject) {
  const stdin = processHandle.stdin
  if (stdin === undefined || typeof stdin === "number") {
    throw new BackendExecutionError("BACKEND_UNAVAILABLE", "Codex app-server stdin is unavailable")
  }
  await Promise.resolve(stdin.write(JSON.stringify(value) + "\n"))
  await Promise.resolve(stdin.flush?.())
}

async function response(reader: ReturnType<typeof lineReader>, requestID: number, signal?: AbortSignal) {
  while (true) {
    if (signal?.aborted) throw signal.reason ?? new DOMException("Aborted", "AbortError")
    const value = await reader.next()
    if (!value) throw new BackendExecutionError("BACKEND_UNAVAILABLE", "Codex app-server closed before replying")
    if (value.id !== requestID) continue
    if (value.error) throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", errorText(value.error), value.error)
    return value
  }
}

async function initialize(handle: ReturnType<typeof Bun.spawn>, reader: ReturnType<typeof lineReader>, signal?: AbortSignal) {
  await write(handle, {
    id: 1,
    method: "initialize",
    params: { clientInfo: { name: "base-harness", title: "Base Harness", version: "2.0.0" } },
  })
  const result = await response(reader, 1, signal)
  await write(handle, { method: "initialized", params: {} })
  return result
}

async function capabilities(): Promise<BackendCapabilities> {
  const handle = await start()
  const reader = lineReader(handle.stdout)
  try {
    await initialize(handle, reader)
    await write(handle, { id: 2, method: "model/list", params: { cursor: null, includeHidden: false } })
    const result = await response(reader, 2)
    const modelDetails = modelsFrom(result)
    if (!modelDetails.length) throw new BackendExecutionError("BACKEND_AUTH_REQUIRED", "Codex returned no available models")
    const autonomousDecision = { protocol: "autonomous-decision-v1" as const, resourceUsage: "reported-v1" as const }
    const raw = JSON.stringify({ modelDetails, autonomousDecision })
    return {
      adapterID: id,
      backendId: id,
      kind: "agent_runtime",
      revision: createHash("sha256").update(raw).digest("hex"),
      models: modelDetails.map((model) => model.modelId),
      reasoningEfforts: [...new Set(modelDetails.flatMap((model) => model.reasoningEfforts))],
      reasoningOption: "reasoning_effort",
      modelDetails,
      autonomousDecision,
    }
  } finally {
    await reader.cancel().catch(() => undefined)
    handle.kill()
  }
}

async function hostWorkspacePath(p: string): Promise<string> {
  if (process.platform === "linux" && command().endsWith(".exe")) {
    try {
      const proc = Bun.spawn(["wslpath", "-w", p])
      const out = await new Response(proc.stdout).text()
      if (out.trim()) return out.trim()
    } catch {}
  }
  return p
}

async function execute(input: BackendExecutionInput): Promise<BackendExecutionResult> {
  const discovered = await capabilities()
  if (input.selection.capabilityRevision && input.selection.capabilityRevision !== discovered.revision) {
    throw new BackendExecutionError("BACKEND_CAPABILITY_STALE", "Codex model capabilities changed after selection")
  }
  const model = discovered.modelDetails?.find((item) => item.modelId === input.selection.modelId)
  if (!model) throw new BackendExecutionError("BACKEND_MODEL_UNAVAILABLE", "Selected Codex model is unavailable: " + input.selection.modelId)
  const effort = input.selection.nativeOptions.reasoning_effort
  if (effort && model.reasoningEfforts.length && !model.reasoningEfforts.includes(effort)) {
    throw new BackendExecutionError("BACKEND_OPTION_UNSUPPORTED", "Selected Codex reasoning effort is unsupported: " + effort)
  }
  for (const key of Object.keys(input.selection.nativeOptions)) {
    if (key !== "reasoning_effort") throw new BackendExecutionError("BACKEND_OPTION_UNSUPPORTED", "Unsupported Codex option: " + key)
  }

  const managed = await createManagedWorkspace(input.sessionID, input.workspace)
  const hostCwd = await hostWorkspacePath(managed.root)
  const handle = await start()
  const reader = lineReader(handle.stdout)
  const timeout = setTimeout(() => handle.kill(), timeoutMs)
  const abort = () => handle.kill()
  input.signal?.addEventListener("abort", abort, { once: true })
  try {
    await initialize(handle, reader, input.signal)
    await write(handle, {
      id: 2,
      method: "thread/start",
      params: {
        cwd: hostCwd,
        model: input.selection.modelId,
      },
    })
    const thread = await response(reader, 2, input.signal)
    const threadResult = record(thread.result)
    const nestedThread = record(threadResult?.thread)
    const resolvedThreadID = typeof nestedThread?.id === "string"
      ? nestedThread.id
      : typeof threadResult?.threadId === "string"
        ? threadResult.threadId
      : typeof threadResult?.id === "string"
        ? threadResult.id
        : undefined
    if (!resolvedThreadID) throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Codex did not return a thread id")
    await write(handle, {
      id: 3,
      method: "turn/start",
      params: {
          threadId: resolvedThreadID,
          cwd: hostCwd,
          model: input.selection.modelId,
          effort,
          input: [{ type: "text", text: input.prompt }],
          sandboxPolicy: {
            type: "workspaceWrite",
            writableRoots: [hostCwd],
            networkAccess: process.env.BASE_HARNESS_CODEX_NETWORK === "1",
          },
        },
    })
    await response(reader, 3, input.signal)
    let output = ""
    let modelTokens: number | undefined
    while (true) {
      const event = await reader.next()
      if (!event) throw new BackendExecutionError("BACKEND_RUN_FAILED", "Codex app-server closed during execution")
      if (event.error) throw new BackendExecutionError("BACKEND_RUN_FAILED", errorText(event.error), event.error)
      const method = typeof event.method === "string" ? event.method : ""
      const params = record(event.params)
      const observedTokens = reportedTokens(event)
      if (observedTokens !== undefined) modelTokens = Math.max(modelTokens ?? 0, observedTokens)
      const delta = typeof params?.delta === "string" ? params.delta : typeof params?.text === "string" ? params.text : ""
      if (method.includes("agentMessage") && delta) output += delta
      if (method === "turn/completed" || method === "turn/complete") {
        const turn = record(params?.turn)
        if (turn?.status === "failed" || turn?.error) {
          throw new BackendExecutionError("BACKEND_RUN_FAILED", errorText(turn.error ?? turn))
        }
        break
      }
      if (method === "turn/failed" || method === "turn/error") throw new BackendExecutionError("BACKEND_RUN_FAILED", errorText(params))
    }
    if (input.phase === "autonomous_decision" && modelTokens === undefined) {
      throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Codex autonomous execution did not report token usage")
    }
    const changedFiles = input.mutationPolicy === "forbid" ? [] : await managed.captureChanges(input.routeWrite)
    return {
      output,
      changedFiles,
      capabilityRevision: discovered.revision,
      backendId: id,
      modelId: input.selection.modelId,
      nativeOptions: input.selection.nativeOptions,
      ...(modelTokens === undefined ? {} : { resourceUsage: { modelTokens, costMinorUnits: 0 } }),
    }
  } finally {
    clearTimeout(timeout)
    input.signal?.removeEventListener("abort", abort)
    handle.kill()
    await reader.cancel().catch(() => undefined)
    await handle.exited.catch(() => undefined)
    await managed.dispose()
  }
}

export const CodexAppServer: ExecutionBackend = {
  id,
  kind: "agent_runtime",
  selectionFromEnvironment() {
    const envBackend = process.env.BASE_HARNESS_EXECUTION_BACKEND
    if (envBackend && envBackend !== id) return undefined
    const modelId = process.env.BASE_HARNESS_EXECUTION_MODEL ?? process.env.BASE_HARNESS_MODEL
    const effort = process.env.BASE_HARNESS_EXECUTION_EFFORT
    if (modelId) {
      return {
        adapterID: id,
        modelID: modelId,
        options: effort ? { reasoning_effort: effort } : undefined,
      }
    }
    return undefined
  },
  discover: capabilities,
  execute,
}
