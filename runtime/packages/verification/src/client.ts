import { delimiter, dirname, resolve } from "node:path"
import {
  SIDECAR_PROTOCOL_VERSION,
  type ObserveActionInput,
  type OpenRunInput,
  type ProtocolEnvelope,
  type VerificationClient,
  type VerificationStatus,
} from "./types"

interface ClientOptions {
  command?: string[]
  cwd?: string
  env?: Record<string, string | undefined>
  timeoutMs?: number
}

interface PendingRequest {
  resolve(value: VerificationStatus | Record<string, unknown>): void
  reject(error: Error): void
  timer: ReturnType<typeof setTimeout>
}

export class VerificationClientError extends Error {
  constructor(
    readonly failureKind: string,
    message: string,
  ) {
    super(message)
    this.name = "VerificationClientError"
  }
}

const inactiveStatus = (runId: string, scopeId: string): VerificationStatus => ({
  state: "inactive",
  goal: "",
  runId,
  scopeId,
  rootScopeId: scopeId,
  evidenceRefs: [],
  candidateRefs: [],
  readyRef: null,
  maxSameFailureRepairs: 2,
})

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)

const asStatus = (
  value: Record<string, unknown>,
  current: VerificationStatus,
): VerificationStatus => ({
  ...current,
  ...value,
  state: typeof value.state === "string" ? (value.state as VerificationStatus["state"]) : current.state,
  evidenceRefs: Array.isArray(value.evidenceRefs) ? (value.evidenceRefs as VerificationStatus["evidenceRefs"]) : current.evidenceRefs,
  candidateRefs: Array.isArray(value.candidateRefs) ? (value.candidateRefs as VerificationStatus["candidateRefs"]) : current.candidateRefs,
})

function defaultCommand(): string[] {
  const explicit = process.env.BASE_HARNESS_VERIFIER
  if (explicit) return [explicit]
  const name = process.platform === "win32" ? "base-harness-verifier.exe" : "base-harness-verifier"
  const packaged = resolve(dirname(process.execPath), name)
  if (Bun.file(packaged).size > 0) return [packaged]
  return [process.env.BASE_HARNESS_PYTHON ?? (process.platform === "win32" ? "python" : "python3"), "-m", "harness.verified_sidecar"]
}

export class ProcessVerificationClient implements VerificationClient {
  readonly runId: string
  readonly rootScopeId: string
  private readonly process: ReturnType<typeof Bun.spawn>
  private readonly input: {
    write(value: string): number | Promise<number>
    flush(): number | Promise<number>
    end(error?: Error): void
  }
  private readonly output: ReadableStream<Uint8Array>
  private readonly errorOutput: ReadableStream<Uint8Array>
  private readonly pending = new Map<string, PendingRequest>()
  private readonly listeners = new Set<(status: VerificationStatus) => void>()
  private readonly timeoutMs: number
  private current: VerificationStatus
  private sequence = 0
  private disposed = false

  private constructor(runId: string, rootScopeId: string, options: ClientOptions) {
    this.runId = runId
    this.rootScopeId = rootScopeId
    this.timeoutMs = options.timeoutMs ?? 30_000
    this.current = inactiveStatus(runId, rootScopeId)
    const pythonPath = resolve(import.meta.dir, "../../../../src")
    const existingPythonPath = process.env.PYTHONPATH
    this.process = Bun.spawn(options.command ?? defaultCommand(), {
      cwd: options.cwd,
      env: {
        ...process.env,
        ...options.env,
        PYTHONPATH: existingPythonPath ? pythonPath + delimiter + existingPythonPath : pythonPath,
      },
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
    })
    if (
      !this.process.stdin ||
      typeof this.process.stdin === "number" ||
      !this.process.stdout ||
      typeof this.process.stdout === "number" ||
      !this.process.stderr ||
      typeof this.process.stderr === "number"
    ) {
      throw new Error("Verifier process did not expose piped stdio")
    }
    this.input = this.process.stdin
    this.output = this.process.stdout
    this.errorOutput = this.process.stderr
    void this.readStdout()
    void this.readStderr()
    void this.watchExit()
  }

  static async start(
    input: OpenRunInput,
    options: ClientOptions = {},
  ): Promise<ProcessVerificationClient> {
    const client = new ProcessVerificationClient(input.runId, input.scopeId, options)
    client.update({ ...client.current, state: "starting" })
    const hello = await client.request<Record<string, unknown>>("hello", {}, input.scopeId)
    if (hello.protocolVersion !== SIDECAR_PROTOCOL_VERSION) {
      await client.fail(
        "harness_protocol_version_mismatch",
        "Verifier protocol version does not match the execution core.",
      )
      throw new VerificationClientError(
        "harness_protocol_version_mismatch",
        "Verifier protocol version mismatch",
      )
    }
    await client.open(input)
    return client
  }

  snapshot(): VerificationStatus {
    return this.current
  }

  subscribe(listener: (status: VerificationStatus) => void): () => void {
    this.listeners.add(listener)
    listener(this.current)
    return () => this.listeners.delete(listener)
  }

  async open(input: OpenRunInput): Promise<VerificationStatus> {
    return this.statusRequest("run.open", {
      workspace: input.workspace,
      goalContract: input.goalContract,
    }, input.scopeId)
  }

  async openScope(scopeId: string, parentScopeId: string): Promise<VerificationStatus> {
    return this.statusRequest("scope.open", { parentScopeId }, scopeId)
  }

  async observe(input: ObserveActionInput): Promise<VerificationStatus> {
    const { scopeId = this.rootScopeId, ...payload } = input
    return this.statusRequest("action.observe", payload, scopeId)
  }

  async verify(
    reason: "automatic" | "manual" | "completion",
    scopeId = this.rootScopeId,
  ): Promise<VerificationStatus> {
    return this.statusRequest("verify.request", { reason }, scopeId)
  }

  async status(scopeId = this.rootScopeId): Promise<VerificationStatus> {
    return this.statusRequest("status.get", {}, scopeId)
  }

  async close(): Promise<VerificationStatus> {
    return this.statusRequest("run.close", {}, this.rootScopeId)
  }

  async dispose(): Promise<void> {
    if (this.disposed) return
    this.disposed = true
    try {
      if (this.current.state !== "closed") await this.close()
    } catch {
      // A crashed verifier is already fail-closed.
    }
    this.input.end()
    await Promise.race([
      this.process.exited,
      Bun.sleep(1_000).then(() => {
        this.process.kill()
      }),
    ])
  }

  private async statusRequest(
    type: string,
    payload: Record<string, unknown>,
    scopeId: string,
  ): Promise<VerificationStatus> {
    const response = await this.request<Record<string, unknown>>(type, payload, scopeId)
    const status = asStatus(response, this.current)
    this.update(status)
    return status
  }

  private request<T extends Record<string, unknown>>(
    type: string,
    payload: Record<string, unknown>,
    scopeId: string,
  ): Promise<T> {
    if (this.disposed) return Promise.reject(new Error("Verifier client is disposed"))
    const id = this.runId + ":" + String(++this.sequence)
    const envelope: ProtocolEnvelope = {
      version: SIDECAR_PROTOCOL_VERSION,
      id,
      runId: this.runId,
      scopeId,
      type,
      payload,
    }
    return new Promise<T>((resolveRequest, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        void this.fail("harness_verifier_timeout", "Verifier did not respond before the protocol deadline.")
        reject(new Error("Verifier request timed out: " + type))
      }, this.timeoutMs)
      this.pending.set(id, {
        resolve: (value) => resolveRequest(value as T),
        reject,
        timer,
      })
      this.input.write(JSON.stringify(envelope) + "\n")
      void this.input.flush()
    })
  }

  private async readStdout(): Promise<void> {
    const reader = this.output.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    while (true) {
      const next = await reader.read()
      if (next.done) break
      buffer += decoder.decode(next.value, { stream: true })
      let newline = buffer.indexOf("\n")
      while (newline >= 0) {
        const line = buffer.slice(0, newline).trim()
        buffer = buffer.slice(newline + 1)
        if (line) this.receive(line)
        newline = buffer.indexOf("\n")
      }
    }
    if (buffer.trim()) this.receive(buffer.trim())
  }

  private async readStderr(): Promise<void> {
    const reader = this.errorOutput.getReader()
    while (!(await reader.read()).done) {
      // stderr is intentionally not promoted to evidence or user-visible Ready.
    }
  }

  private receive(line: string): void {
    let envelope: unknown
    try {
      envelope = JSON.parse(line)
    } catch {
      void this.fail("harness_protocol_error", "Verifier emitted malformed NDJSON.")
      return
    }
    if (!isRecord(envelope) || envelope.version !== SIDECAR_PROTOCOL_VERSION) {
      void this.fail("harness_protocol_version_mismatch", "Verifier emitted an incompatible envelope.")
      return
    }
    const id = typeof envelope.id === "string" ? envelope.id : ""
    const pending = this.pending.get(id)
    if (!pending) return
    this.pending.delete(id)
    clearTimeout(pending.timer)
    const payload = envelope.payload
    if (!isRecord(payload)) {
      pending.reject(new VerificationClientError("harness_protocol_error", "Verifier response payload is invalid"))
      void this.fail("harness_protocol_error", "Verifier response payload is invalid.")
      return
    }
    if (envelope.type === "failure") {
      const message = typeof payload.message === "string" ? payload.message : "Verifier rejected the protocol request"
      const failureKind =
        typeof payload.failureKind === "string" ? payload.failureKind : "harness_protocol_error"
      pending.reject(new VerificationClientError(failureKind, message))
      this.update(asStatus(payload, this.current))
      return
    }
    pending.resolve(payload)
  }

  private async watchExit(): Promise<void> {
    const code = await this.process.exited
    if (!this.disposed && code !== 0) {
      await this.fail(
        "harness_verifier_unavailable",
        "Verifier exited unexpectedly with code " + String(code) + ".",
      )
    }
  }

  private async fail(failureKind: string, message: string): Promise<void> {
    this.update({
      ...this.current,
      state: "failure",
      outcome: "failure",
      failureKind,
      message,
      readyRef: null,
    })
    for (const request of this.pending.values()) {
      clearTimeout(request.timer)
      request.reject(new VerificationClientError(failureKind, message))
    }
    this.pending.clear()
  }

  private update(status: VerificationStatus): void {
    this.current = status
    for (const listener of this.listeners) listener(status)
  }
}

export const createVerificationClient = (
  input: OpenRunInput,
  options?: ClientOptions,
): Promise<ProcessVerificationClient> => ProcessVerificationClient.start(input, options)
