const REQUEST_TIMEOUT_MS = 8_000

export interface CodexAppServerModel {
  id: string
  model: string
  displayName: string
  defaultReasoningEffort?: string
  supportedReasoningEfforts: string[]
  inputModalities: string[]
  isDefault: boolean
}

export interface CodexAppServerCatalog {
  models: CodexAppServerModel[]
}

type PendingRequest = {
  resolve(value: unknown): void
  reject(error: Error): void
  timeout: ReturnType<typeof setTimeout>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function executableCommand(executable: string) {
  if (process.platform !== "win32" || !/\.(cmd|bat)$/i.test(executable)) return [executable, "app-server"]
  const comspec = process.env.ComSpec || process.env.COMSPEC || "cmd.exe"
  return [comspec, "/d", "/s", "/c", `"${executable}" app-server`]
}

function parseModel(value: unknown): CodexAppServerModel | undefined {
  if (!isRecord(value)) return undefined
  const id = typeof value.id === "string" ? value.id.trim() : ""
  const model = typeof value.model === "string" ? value.model.trim() : ""
  if (!id || !model) return undefined

  const efforts = Array.isArray(value.supportedReasoningEfforts)
    ? value.supportedReasoningEfforts.flatMap((entry) => {
        if (!isRecord(entry) || typeof entry.reasoningEffort !== "string") return []
        const effort = entry.reasoningEffort.trim()
        return effort ? [effort] : []
      })
    : []

  return {
    id,
    model,
    displayName: typeof value.displayName === "string" && value.displayName.trim() ? value.displayName : model,
    defaultReasoningEffort:
      typeof value.defaultReasoningEffort === "string" && value.defaultReasoningEffort.trim()
        ? value.defaultReasoningEffort
        : undefined,
    supportedReasoningEfforts: [...new Set(efforts)],
    inputModalities: Array.isArray(value.inputModalities)
      ? value.inputModalities.filter((item): item is string => typeof item === "string")
      : [],
    isDefault: value.isDefault === true,
  }
}

/**
 * Reads Codex's authoritative picker catalog over the documented app-server
 * protocol. Authentication and model execution remain owned by Base Harness's
 * OpenAI OAuth provider; this process is discovery-only.
 */
export async function discoverCodexAppServerCatalog(): Promise<CodexAppServerCatalog | undefined> {
  const configured = process.env.BASE_HARNESS_CODEX_APP_SERVER_PATH?.trim()
  const executable = configured || Bun.which("codex")
  if (!executable) return undefined

  let child: Bun.Subprocess<"pipe", "pipe", "ignore">
  try {
    child = Bun.spawn(executableCommand(executable), {
      stdin: "pipe",
      stdout: "pipe",
      stderr: "ignore",
      env: process.env,
    })
  } catch {
    return undefined
  }

  const pending = new Map<number, PendingRequest>()
  let sequence = 0
  let closed = false

  const rejectPending = (error: Error) => {
    if (closed) return
    closed = true
    for (const request of pending.values()) {
      clearTimeout(request.timeout)
      request.reject(error)
    }
    pending.clear()
  }

  const dispatch = (line: string) => {
    let message: unknown
    try {
      message = JSON.parse(line)
    } catch {
      return
    }
    if (!isRecord(message) || typeof message.id !== "number") return
    const request = pending.get(message.id)
    if (!request) return
    pending.delete(message.id)
    clearTimeout(request.timeout)
    if (isRecord(message.error)) {
      const code = typeof message.error.code === "number" ? ` (${message.error.code})` : ""
      const detail = typeof message.error.message === "string" ? message.error.message : "Unknown app-server error"
      request.reject(new Error(`Codex app-server request failed${code}: ${detail}`))
      return
    }
    request.resolve(message.result)
  }

  const read = async () => {
    const reader = child.stdout.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    try {
      while (true) {
        const chunk = await reader.read()
        if (chunk.done) break
        buffer += decoder.decode(chunk.value, { stream: true })
        while (true) {
          const newline = buffer.indexOf("\n")
          if (newline < 0) break
          const line = buffer.slice(0, newline).trim()
          buffer = buffer.slice(newline + 1)
          if (line) dispatch(line)
        }
      }
      const tail = buffer.trim()
      if (tail) dispatch(tail)
      rejectPending(new Error("Codex app-server closed before completing model discovery"))
    } catch (error) {
      rejectPending(error instanceof Error ? error : new Error(String(error)))
    }
  }

  const write = (message: unknown) => {
    if (closed) throw new Error("Codex app-server is closed")
    child.stdin.write(`${JSON.stringify(message)}\n`)
    child.stdin.flush()
  }

  const request = <T>(method: string, params: Record<string, unknown>): Promise<T> => {
    const id = ++sequence
    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(() => {
        pending.delete(id)
        reject(new Error(`Codex app-server request timed out: ${method}`))
      }, REQUEST_TIMEOUT_MS)
      pending.set(id, {
        resolve: (value) => resolve(value as T),
        reject,
        timeout,
      })
      try {
        write({ method, id, params })
      } catch (error) {
        pending.delete(id)
        clearTimeout(timeout)
        reject(error instanceof Error ? error : new Error(String(error)))
      }
    })
  }

  void read()
  try {
    await request("initialize", {
      clientInfo: {
        name: "base_harness",
        title: "Base Harness",
        version: "2.0.0",
      },
    })
    write({ method: "initialized", params: {} })

    const models: CodexAppServerModel[] = []
    let cursor: string | undefined
    do {
      const result = await request<unknown>("model/list", {
        limit: 100,
        includeHidden: false,
        ...(cursor ? { cursor } : {}),
      })
      if (!isRecord(result) || !Array.isArray(result.data)) throw new Error("Invalid Codex model/list response")
      models.push(...result.data.flatMap((entry) => (parseModel(entry) ? [parseModel(entry)!] : [])))
      cursor = typeof result.nextCursor === "string" && result.nextCursor ? result.nextCursor : undefined
    } while (cursor)

    return models.length ? { models } : undefined
  } catch {
    return undefined
  } finally {
    closed = true
    for (const item of pending.values()) clearTimeout(item.timeout)
    pending.clear()
    try {
      child.stdin.end()
    } catch {}
    child.kill()
  }
}
