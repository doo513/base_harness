import { createHash } from "node:crypto"
import { resolve } from "node:path"
import type { ObservationReport } from "@base-harness/domain-contracts"
import { assertAutonomousSchema, assertJson, canonicalJson, parseObservationReport, sameRef, sameSubject } from "@base-harness/kernel"
import {
  MEASUREMENT_PROTOCOL_VERSION, type MeasurementClient, type MeasurementCommandExecutor, type MeasurementRequest,
} from "./measurement-types"

export interface MeasurementClientOptions {
  command?: string[]
  env?: Record<string, string>
  timeoutMs?: number
  /** Trusted composition callback, not an actor-selected executable. */
  executeCommand?: MeasurementCommandExecutor
}
interface Pending {
  taskId: string
  resolve(value: unknown): void
  reject(error: Error): void
  timer: ReturnType<typeof setTimeout>
}
const sha256 = (value: string) => createHash("sha256").update(value).digest("hex")
function responseProtocolFailure(error: unknown): Error {
  if (error instanceof Error && /^MEASUREMENT_(?:RESPONSE|PROTOCOL)/.test(error.message)) return error
  return new Error("MEASUREMENT_RESPONSE_PROTOCOL", { cause: error })
}
function validateManifest(request: MeasurementRequest): void {
  const manifest = JSON.parse(request.manifestJson)
  assertJson(manifest)
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest) ||
      Object.keys(manifest).sort().join(",") !== "dependencies,files,kind" || manifest.kind !== request.subject.kind ||
      !Array.isArray(manifest.files) || !Array.isArray(manifest.dependencies)) throw new Error("MEASUREMENT_MANIFEST_SCHEMA")
  const paths = new Set<string>()
  let totalBytes = 0
  for (const entry of manifest.files) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry) || Object.keys(entry).sort().join(",") !== "path,sha256,size" ||
        typeof entry.path !== "string" || entry.path.includes("\\") || entry.path.includes("\u0000") ||
        entry.path.split("/").some((part) => !part || part === "." || part === ".." || part.includes(":")) ||
        typeof entry.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(entry.sha256) ||
        typeof entry.size !== "number" || !Number.isSafeInteger(entry.size) || entry.size < 0 || paths.has(entry.path)) {
      throw new Error("MEASUREMENT_MANIFEST_SCHEMA")
    }
    totalBytes += entry.size
    if (totalBytes > 10 * 1024 * 1024) throw new Error("MEASUREMENT_MANIFEST_LIMIT")
    paths.add(entry.path)
  }
  for (const dependency of manifest.dependencies) assertAutonomousSchema("subject", dependency)
}
function freeze<T>(value: T): T {
  if (value && typeof value === "object") {
    for (const child of Object.values(value)) freeze(child)
    Object.freeze(value)
  }
  return value
}

/** A dedicated v5 pipe. Legacy v4 statuses never enter this observation channel. */
export class ProcessMeasurementClient implements MeasurementClient {
  private readonly process: ReturnType<typeof Bun.spawn>
  private readonly pending = new Map<string, Pending>()
  private readonly requests = new Map<string, { fingerprint: string; result: Promise<ObservationReport> }>()
  private readonly authenticated = new WeakSet<object>()
  private readonly shutdown = new AbortController()
  private failure?: Error
  private disposed = false
  private readonly timeoutMs: number

  private constructor(readonly runId: string, private readonly options: MeasurementClientOptions) {
    this.timeoutMs = options.timeoutMs ?? 30_000
    if (!runId.trim() || !Number.isSafeInteger(this.timeoutMs) || this.timeoutMs <= 0) throw new Error("MEASUREMENT_CLIENT_OPTIONS")
    const pythonPath = resolve(import.meta.dir, "../../../../src")
    const inherited = Object.fromEntries(["PATH", "Path", "PATHEXT", "SystemRoot", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP", "LANG", "LC_ALL"]
      .flatMap((key) => process.env[key] === undefined ? [] : [[key, process.env[key]!]]))
    this.process = Bun.spawn(options.command ?? [process.env.BASE_HARNESS_PYTHON ?? (process.platform === "win32" ? "python" : "python3"), "-m", "harness.measurement_sidecar"], {
      cwd: resolve(pythonPath, ".."), env: { ...inherited, ...options.env, PYTHONPATH: pythonPath, PYTHONIOENCODING: "utf-8" },
      stdin: "pipe", stdout: "pipe", stderr: "pipe",
    })
    const child = this.process
    void this.readOutput().catch((error) => this.fail(responseProtocolFailure(error)))
    // Drain without exposing raw process stderr as trusted observations.
    void (async () => { for await (const _ of streamChunks(child.stderr as ReadableStream<Uint8Array>)) {} })().catch(() => this.fail(new Error("MEASUREMENT_STDERR_ERROR")))
    void this.process.exited.then(() => {
      if (!this.disposed) this.fail(new Error("MEASUREMENT_PROCESS_EXITED"))
    }).catch(() => this.fail(new Error("MEASUREMENT_PROCESS_UNOBSERVABLE")))
  }

  static async start(runId: string, snapshotRoot: string, options: MeasurementClientOptions = {}): Promise<ProcessMeasurementClient> {
    const client = new ProcessMeasurementClient(runId, options)
    try {
      const hello = await client.request("control:hello", "root", "hello", {})
      if (canonicalJson(hello) !== canonicalJson({ protocolVersion: 5, semantics: "observations-only" })) {
        throw new Error("MEASUREMENT_PROTOCOL_VERSION")
      }
      const opened = await client.request("control:open", "root", "run.open", { snapshotRoot })
      if (canonicalJson(opened) !== '{"opened":true}') throw new Error("MEASUREMENT_OPEN_PROTOCOL")
      return client
    } catch (error) {
      await client.dispose()
      throw error
    }
  }

  authenticates(report: ObservationReport): boolean { return this.authenticated.has(report) }

  measure(input: MeasurementRequest, signal: AbortSignal): Promise<ObservationReport> {
    if (this.failure) return Promise.reject(this.failure)
    if (this.disposed || signal.aborted) return Promise.reject(new Error("MEASUREMENT_CANCELLED"))
    let request: MeasurementRequest
    let fingerprint: string
    try {
      assertJson(input)
      if (Object.keys(input).sort().join(",") !== "check,environmentHash,manifestJson,requestId,runId,subject,taskId" ||
          input.runId !== this.runId || !input.requestId.trim() || !input.taskId.trim() || input.requestId.startsWith("control:")) {
        throw new Error("MEASUREMENT_REQUEST_BINDING")
      }
      assertAutonomousSchema("check", input.check)
      assertAutonomousSchema("subject", input.subject)
      if (input.check.executorId !== "python-measurement") throw new Error("MEASUREMENT_EXECUTOR_BINDING")
      if (!/^[a-f0-9]{64}$/.test(input.environmentHash) || !input.check.supportedSubjects.includes(input.subject.kind)) {
        throw new Error("MEASUREMENT_REQUEST_SCHEMA")
      }
      if (sha256(input.manifestJson) !== input.subject.sha256) throw new Error("MEASUREMENT_SUBJECT_DIGEST")
      validateManifest(input)
      request = freeze(structuredClone(input))
      fingerprint = canonicalJson(request)
    } catch (error) { return Promise.reject(error) }
    const previous = this.requests.get(request.requestId)
    if (previous) return previous.fingerprint === fingerprint ? previous.result : Promise.reject(new Error("MEASUREMENT_REQUEST_CONFLICT"))
    // Start in a microtask after recording the promise so re-entrant callers replay it.
    const result = Promise.resolve().then(async () => {
      const activeSignal = AbortSignal.any([signal, this.shutdown.signal, AbortSignal.timeout(request.check.timeoutMs)])
      activeSignal.throwIfAborted()
      const params = request.check.parameters
      const isCommand = params !== null && typeof params === "object" && !Array.isArray(params) && params.kind === "command"
      if (isCommand && (Object.keys(params).sort().join(",") !== "argv,cwd,expectedExitCode,kind" ||
          !Array.isArray(params.argv) || !params.argv.length || !params.argv.every((arg) => typeof arg === "string") ||
          typeof params.argv[0] !== "string" || !params.argv[0].trim() || typeof params.cwd !== "string" || !params.cwd.trim() ||
          !Number.isSafeInteger(params.expectedExitCode))) throw new Error("MEASUREMENT_COMMAND_SCHEMA")
      if (isCommand && !request.check.requiredCapabilities.includes("execute")) throw new Error("MEASUREMENT_COMMAND_CAPABILITY")
      const capture = isCommand && this.options.executeCommand ? await this.options.executeCommand(request, activeSignal) : undefined
      // A timeout reported by the owned adapter is an observation; user cancellation
      // or disposal is not permission to publish a late result into the current Run.
      if (signal.aborted || this.shutdown.signal.aborted) throw new Error("MEASUREMENT_CANCELLED")
      const payload = { subject: request.subject, manifestJson: request.manifestJson, check: request.check,
        environmentHash: request.environmentHash, ...(capture === undefined ? {} : { capture }) }
      const raw = await this.request(request.requestId, request.taskId, "measure", payload)
      if (signal.aborted || this.shutdown.signal.aborted) throw new Error("MEASUREMENT_CANCELLED")
      let report: ObservationReport
      try {
        report = parseObservationReport(raw)
        if (report.runId !== request.runId || report.taskId !== request.taskId || report.requestId !== request.requestId ||
            !sameSubject(report.subject, request.subject) || !sameRef(report.checkRef, request.check.ref) ||
            report.environmentHash !== request.environmentHash || report.producer.id !== "python-measurement" || report.producer.revision !== "5") {
          throw new Error("MEASUREMENT_RESPONSE_BINDING")
        }
      } catch (error) {
        const failure = responseProtocolFailure(error)
        this.fail(failure)
        throw failure
      }
      freeze(report)
      this.authenticated.add(report)
      return report
    })
    this.requests.set(request.requestId, { fingerprint, result })
    return result
  }

  async dispose(): Promise<void> {
    if (!this.disposed) {
      this.disposed = true
      this.shutdown.abort(new Error("MEASUREMENT_DISPOSED"))
      this.fail(new Error("MEASUREMENT_DISPOSED"))
    }
    await this.process.exited
  }

  private fail(error: Error): void {
    this.failure ??= error
    for (const item of this.pending.values()) { clearTimeout(item.timer); item.reject(this.failure) }
    this.pending.clear()
    this.shutdown.abort(this.failure)
    this.process.kill()
  }

  private request(id: string, taskId: string, type: string, payload: unknown): Promise<unknown> {
    if (this.failure || this.disposed) return Promise.reject(this.failure ?? new Error("MEASUREMENT_DISPOSED"))
    if (this.pending.has(id)) return Promise.reject(new Error("MEASUREMENT_DUPLICATE_PENDING"))
    const body = canonicalJson({ version: MEASUREMENT_PROTOCOL_VERSION, id, runId: this.runId, scopeId: taskId, type, payload }) + "\n"
    if (Buffer.byteLength(body) > 40 * 1024 * 1024) return Promise.reject(new Error("MEASUREMENT_MESSAGE_LIMIT"))
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => this.fail(new Error("MEASUREMENT_TRANSPORT_TIMEOUT")), this.timeoutMs)
      this.pending.set(id, { taskId, resolve, reject, timer })
      try {
        const stdin = this.process.stdin
        if (!stdin || typeof stdin === "number") throw new Error("MEASUREMENT_STDIN_UNAVAILABLE")
        stdin.write(body)
        void Promise.resolve(stdin.flush()).catch(() => this.fail(new Error("MEASUREMENT_STDIN_ERROR")))
      } catch (error) { this.fail(error instanceof Error ? error : new Error("MEASUREMENT_STDIN_ERROR")) }
    })
  }

  private async readOutput(): Promise<void> {
    const decoder = new TextDecoder("utf-8", { fatal: true })
    let buffer = ""
    for await (const chunk of streamChunks(this.process.stdout as ReadableStream<Uint8Array>)) {
      buffer += decoder.decode(chunk, { stream: true })
      if (buffer.length > 40 * 1024 * 1024) throw new Error("MEASUREMENT_RESPONSE_LIMIT")
      let newline: number
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1)
        const envelope = JSON.parse(line)
        assertJson(envelope)
        if (!envelope || typeof envelope !== "object" || Array.isArray(envelope) ||
            Object.keys(envelope).sort().join(",") !== "id,payload,runId,scopeId,type,version" ||
            envelope.version !== 5 || envelope.runId !== this.runId || typeof envelope.id !== "string") {
          throw new Error("MEASUREMENT_RESPONSE_PROTOCOL")
        }
        const pending = this.pending.get(envelope.id)
        if (!pending || envelope.scopeId !== pending.taskId || envelope.type !== "response") {
          throw new Error("MEASUREMENT_RESPONSE_PROTOCOL")
        }
        this.pending.delete(envelope.id); clearTimeout(pending.timer); pending.resolve(envelope.payload)
      }
    }
    buffer += decoder.decode()
    if (buffer.length || this.pending.size) throw new Error("MEASUREMENT_RESPONSE_TRUNCATED")
  }
}

/** Use the standard reader API; consumers need not enable DOM.AsyncIterable. */
async function* streamChunks(stream: ReadableStream<Uint8Array>) {
  const reader = stream.getReader()
  try {
    for (;;) {
      const next = await reader.read()
      if (next.done) return
      yield next.value
    }
  } finally { reader.releaseLock() }
}
