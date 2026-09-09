import { dirname, resolve } from "node:path"
import {
  SIDECAR_PROTOCOL_VERSION,
  type ActionCloseInput,
  type ActionOpenInput,
  type CandidateManifest,
  type GoalContract,
  type ObserveActionInput,
  type OpenRunInput,
  type ProtocolEnvelope,
  type ScopeAttestation,
  type VerificationClient,
  type VerificationStatus,
} from "./types"
import { isTrustedFailureEnvelope } from "./failure"

export interface ClientOptions {
  command?: string[]
  cwd?: string
  env?: Record<string, string | undefined>
  timeoutMs?: number
  redactor?: (value: unknown) => unknown
}

interface PendingRequest {
  scopeId: string
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
  contractStatus: "missing",
  criterionResults: [],
  claimResults: [],
  evidenceFamilies: [],
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
  // Responses are snapshots, not patches. A prior scope's rejection or authority
  // must never fill fields omitted by the next response.
  outcome: typeof value.outcome === "string" ? value.outcome as VerificationStatus["outcome"] : undefined,
  failureKind: typeof value.failureKind === "string" ? value.failureKind : undefined,
  failedCriterion: typeof value.failedCriterion === "string" ? value.failedCriterion : undefined,
  missingEvidence: Array.isArray(value.missingEvidence) ? value.missingEvidence as string[] : [],
  repairScope: typeof value.repairScope === "string" ? value.repairScope : undefined,
  repairScopeId: typeof value.repairScopeId === "string" ? value.repairScopeId : undefined,
  repairCount: typeof value.repairCount === "number" ? value.repairCount : 0,
  failureFingerprint: typeof value.failureFingerprint === "string" ? value.failureFingerprint : undefined,
  message: typeof value.message === "string" ? value.message : undefined,
  readyRef: isRecord(value.readyRef) ? value.readyRef as unknown as VerificationStatus["readyRef"] : null,
  readyEligible: value.readyEligible === true,
  scopeAttestation: isRecord(value.scopeAttestation) ? value.scopeAttestation as unknown as ScopeAttestation : null,
  state: typeof value.state === "string" ? (value.state as VerificationStatus["state"]) : current.state,
  criterionResults: Array.isArray(value.criterionResults)
    ? (value.criterionResults as VerificationStatus["criterionResults"])
    : current.criterionResults,
  claimResults: Array.isArray(value.claimResults)
    ? (value.claimResults as VerificationStatus["claimResults"])
    : current.claimResults,
  evidenceFamilies: Array.isArray(value.evidenceFamilies)
    ? (value.evidenceFamilies as VerificationStatus["evidenceFamilies"])
    : current.evidenceFamilies,
  evidenceRefs: Array.isArray(value.evidenceRefs)
    ? (value.evidenceRefs as VerificationStatus["evidenceRefs"])
    : current.evidenceRefs,
  candidateRefs: Array.isArray(value.candidateRefs)
    ? (value.candidateRefs as VerificationStatus["candidateRefs"])
    : current.candidateRefs,
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
  private readonly redactor: (value: unknown) => unknown
  private current: VerificationStatus
  private sequence = 0
  private disposed = false
  private failed = false

  private constructor(runId: string, rootScopeId: string, options: ClientOptions) {
    this.runId = runId
    this.rootScopeId = rootScopeId
    this.timeoutMs = options.timeoutMs ?? 180_000
    this.redactor = options.redactor ?? ((value) => value)
    this.current = inactiveStatus(runId, rootScopeId)
    const pythonPath = resolve(import.meta.dir, "../../../../src")
    const inherited = Object.fromEntries([
      "PATH", "Path", "PATHEXT", "SystemRoot", "WINDIR", "HOME", "USERPROFILE",
      "TEMP", "TMP", "LOCALAPPDATA", "XDG_STATE_HOME", "LANG", "LC_ALL",
    ].flatMap((key) => process.env[key] === undefined ? [] : [[key, process.env[key]!]]))
    this.process = Bun.spawn(options.command ?? defaultCommand(), {
      cwd: options.cwd ?? resolve(pythonPath, ".."),
      env: {
        ...inherited,
        ...options.env,
        PYTHONPATH: pythonPath,
        PYTHONIOENCODING: "utf-8",
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
    void this.readStdout().catch(() => this.fail("harness_protocol_error", "Verifier stdout could not be read."))
    void this.readStderr().catch(() => this.fail("harness_protocol_error", "Verifier stderr could not be drained."))
    void this.watchExit().catch(() => this.fail("harness_verifier_unavailable", "Verifier process could not be observed."))
  }

  static async start(
    input: OpenRunInput,
    options: ClientOptions = {},
  ): Promise<ProcessVerificationClient> {
    const client = new ProcessVerificationClient(input.runId, input.scopeId, options)
    client.update({ ...client.current, state: "starting" })
    try {
      const hello = await client.request<Record<string, unknown>>("hello", {}, input.scopeId)
      if (hello.protocolVersion !== SIDECAR_PROTOCOL_VERSION) {
        throw new VerificationClientError("harness_protocol_version_mismatch", "Verifier protocol version mismatch")
      }
      await client.open(input)
      return client
    } catch (error) {
      await client.fail(
        error instanceof VerificationClientError ? error.failureKind : "harness_verifier_unavailable",
        error instanceof Error ? error.message : "Verifier startup failed",
      )
      await client.dispose()
      throw error
    }
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
    return this.statusRequest(
      "run.open",
      {
        workspace: input.workspace,
        goalSources: input.goalSources,
        configuredProfile: input.configuredProfile,
        effectiveProfile: input.effectiveProfile,
        escalationReasons: input.escalationReasons,
        ...(input.goalContract ? { goalContract: input.goalContract } : {}),
      },
      input.scopeId,
    )
  }

  async openScope(
    scopeId: string,
    parentScopeId: string,
    options: { kind?: import("./types").VerificationScopeKind; assignedClaimIds?: string[] } = {},
  ): Promise<VerificationStatus> {
    return this.statusRequest("scope.open", { parentScopeId, ...options }, scopeId)
  }

  async proposeContract(contract: GoalContract, scopeId = this.rootScopeId): Promise<VerificationStatus> {
    return this.statusRequest("contract.propose", { contract }, scopeId)
  }

  async amendContract(contract: GoalContract, scopeId = this.rootScopeId): Promise<VerificationStatus> {
    return this.statusRequest("contract.amend", { contract }, scopeId)
  }

  async openAction(input: ActionOpenInput): Promise<{ actionId: string; status: VerificationStatus }> {
    const scopeId = input.scopeId ?? this.rootScopeId
    const actionId = input.actionId ?? this.runId + ":action:" + String(++this.sequence)
    const executionId = input.executionId ?? actionId + ":execution"
    const claimIds =
      input.claimIds ??
      this.current.goalContract?.claims.map((claim) => claim.claimId) ??
      []
    const status = await this.statusRequest(
      "action.open",
      {
        actionId,
        executionId,
        claimIds,
        tool: input.tool,
        input: input.input,
        startedAt: input.startedAt,
      },
      scopeId,
    )
    if (status.outcome && ["repair", "blocked", "needs_input", "failure", "repair_exhausted"].includes(status.outcome)) {
      throw new VerificationClientError(
        status.failureKind ?? "verification_failed",
        status.failedCriterion ?? "Verifier rejected action.open",
      )
    }
    return { actionId, status }
  }

  async closeAction(input: ActionCloseInput): Promise<VerificationStatus> {
    const { scopeId = this.rootScopeId, ...payload } = input
    return this.statusRequest("action.close", payload, scopeId)
  }

  async observe(input: ObserveActionInput): Promise<VerificationStatus> {
    if (input.status === "error" && !isTrustedFailureEnvelope(input.error)) {
      throw new VerificationClientError(
        "harness_untrusted_failure",
        "Only a host-produced FailureEnvelope may be submitted as an execution failure.",
      )
    }
    const opened = await this.openAction(input)
    return this.closeAction({
      scopeId: input.scopeId,
      actionId: opened.actionId,
      status: input.status,
      output: input.output,
      error: input.error,
      metadata: input.status === "error" ? { ...input.metadata, failureEnvelope: input.error } : input.metadata,
    })
  }

  async verify(
    reason: "automatic" | "manual" | "completion",
    scopeId = this.rootScopeId,
    target: { claimIds?: string[]; criterionIds?: string[] } = {},
  ): Promise<VerificationStatus> {
    return this.statusRequest("verify.request", { reason, ...target }, scopeId)
  }

  async attachCandidate(candidate: CandidateManifest): Promise<VerificationStatus> {
    return this.statusRequest("candidate.attach", { candidate }, candidate.scopeId)
  }

  async commitCandidate(attestation: ScopeAttestation, scopeId = this.rootScopeId): Promise<VerificationStatus> {
    const response = await this.request<Record<string, unknown>>("candidate.commit", { attestation }, scopeId)
    const status = asStatus(response, this.current)
    if (response.state === "failure" || response.outcome === "failure") {
      this.update(status)
      throw new VerificationClientError(status.failureKind ?? "harness_verifier_error", status.message ?? "Verifier refused candidate commit")
    }
    const acknowledged = response.committedCandidate
    if (
      !isRecord(acknowledged) ||
      acknowledged.candidateId !== attestation.candidateId ||
      acknowledged.candidateRevision !== attestation.candidateRevision ||
      acknowledged.patchHash !== attestation.patchHash
    ) {
      await this.fail("harness_protocol_error", "Verifier did not acknowledge the committed candidate identity")
      throw new VerificationClientError("harness_protocol_error", "Missing or mismatched candidate commit acknowledgment")
    }
    this.update(status)
    return status
  }

  async reopenScope(scopeId: string): Promise<VerificationStatus> {
    return this.statusRequest("scope.reopen", {}, scopeId)
  }

  async status(scopeId = this.rootScopeId): Promise<VerificationStatus> {
    return this.statusRequest("status.get", {}, scopeId)
  }

  async close(): Promise<VerificationStatus> {
    return this.statusRequest("run.close", {}, this.rootScopeId)
  }

  async dispose(): Promise<void> {
    if (this.disposed) return
    try {
      if (!this.failed && this.current.state !== "closed") await this.close()
    } catch {
      // A crashed verifier is already fail-closed.
    }
    this.disposed = true
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
    if (this.disposed || this.failed) return Promise.reject(new VerificationClientError("harness_verifier_unavailable", "Verifier client is not available"))
    const id = this.runId + ":" + String(++this.sequence)
    const envelope: ProtocolEnvelope = {
      version: SIDECAR_PROTOCOL_VERSION,
      id,
      runId: this.runId,
      scopeId,
      type,
      payload: this.redactor(payload) as Record<string, unknown>,
    }
    return new Promise<T>((resolveRequest, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id)
        void this.fail("harness_verifier_timeout", "Verifier did not respond before the protocol deadline.")
        reject(new VerificationClientError("harness_verifier_timeout", "Verifier request timed out: " + type))
      }, this.timeoutMs)
      this.pending.set(id, {
        scopeId,
        resolve: (value) => resolveRequest(value as T),
        reject,
        timer,
      })
      try {
        this.input.write(JSON.stringify(envelope) + "\n")
        void Promise.resolve(this.input.flush()).catch(() =>
          this.fail("harness_verifier_unavailable", "Verifier stdin could not be flushed."),
        )
      } catch {
        void this.fail("harness_verifier_unavailable", "Verifier stdin could not be written.")
      }
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
      if (Buffer.byteLength(buffer, "utf8") > 10 * 1024 * 1024) {
        await this.fail("harness_protocol_error", "Verifier response exceeded the NDJSON frame limit.")
        return
      }
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
      // stderr has no evidence or Ready authority.
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
    if (
      envelope.runId !== this.runId ||
      envelope.scopeId !== pending.scopeId ||
      (envelope.type !== "response" && envelope.type !== "failure")
    ) {
      void this.fail("harness_protocol_error", "Verifier response identity or type does not match the request.")
      return
    }
    this.pending.delete(id)
    clearTimeout(pending.timer)
    const payload = envelope.payload
    if (!isRecord(payload)) {
      pending.reject(new VerificationClientError("harness_protocol_error", "Verifier response payload is invalid"))
      void this.fail("harness_protocol_error", "Verifier response payload is invalid.")
      return
    }
    if (
      (payload.runId !== undefined && payload.runId !== this.runId) ||
      (payload.scopeId !== undefined && payload.scopeId !== pending.scopeId) ||
      (payload.rootScopeId !== undefined && payload.rootScopeId !== this.rootScopeId)
    ) {
      pending.reject(new VerificationClientError("harness_protocol_error", "Verifier payload identity does not match the request"))
      void this.fail("harness_protocol_error", "Verifier payload identity does not match the request.")
      return
    }
    const correlated = { ...payload, runId: this.runId, scopeId: pending.scopeId, rootScopeId: this.rootScopeId }
    if (envelope.type === "failure") {
      const message = typeof payload.message === "string" ? payload.message : "Verifier rejected the protocol request"
      const failureKind = typeof payload.failureKind === "string" ? payload.failureKind : "harness_protocol_error"
      pending.reject(new VerificationClientError(failureKind, message))
      this.update(asStatus(correlated, this.current))
      return
    }
    if (
      (payload.outcome === "ready" && (
        pending.scopeId !== this.rootScopeId ||
        !isRecord(payload.readyRef) ||
        payload.readyRef.trust !== "verifier_attested"
      )) ||
      (payload.outcome === "scope_verified" && (
        pending.scopeId === this.rootScopeId ||
        !isRecord(payload.scopeAttestation)
      ))
    ) {
      pending.reject(new VerificationClientError("harness_protocol_error", "Verifier attestation scope is invalid"))
      void this.fail("harness_protocol_error", "Verifier attestation scope is invalid.")
      return
    }
    pending.resolve(correlated)
  }

  private async watchExit(): Promise<void> {
    const code = await this.process.exited
    if (!this.disposed && !this.failed && this.current.state !== "closed") {
      await this.fail("harness_verifier_unavailable", "Verifier exited unexpectedly with code " + String(code) + ".")
    }
  }

  private async fail(failureKind: string, message: string): Promise<void> {
    if (this.failed || this.disposed) return
    this.failed = true
    try { this.process.kill() } catch { /* A terminated verifier is already closed. */ }
    this.update({
      ...this.current,
      state: "failure",
      outcome: "failure",
      failureKind,
      message,
      readyRef: null,
      readyEligible: false,
      scopeAttestation: null,
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
