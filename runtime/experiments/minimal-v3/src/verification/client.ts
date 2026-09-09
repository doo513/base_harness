import { randomUUID } from "node:crypto"
import type { SecretRegistry } from "../security/secrets"

const PROTOCOL_VERSION = 4
type Pending = { resolve(value: Record<string, any>): void; reject(error: Error): void; timer: ReturnType<typeof setTimeout> }

export class VerificationProtocolError extends Error {
  constructor(message: string, readonly code = "VERIFIER_PROTOCOL_ERROR") { super(message); this.name = "VerificationProtocolError" }
}

export class SidecarClient {
  private readonly pending = new Map<string, Pending>()
  private buffer = ""
  private stopped = false

  private constructor(
    readonly runId: string,
    readonly rootScopeId: string,
    private readonly processHandle: any,
    private readonly secrets: SecretRegistry,
  ) { void this.readLoop(); void this.watchExit() }

  static async start(runId: string, rootScopeId: string, secrets: SecretRegistry): Promise<SidecarClient> {
    const python = process.env.BASE_HARNESS_PYTHON ?? (process.platform === "win32" ? "python" : "python3")
    const env = Object.fromEntries(["PATH", "Path", "PATHEXT", "SystemRoot", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP", "PYTHONPATH"].flatMap((key) => process.env[key] ? [[key, process.env[key]!]] : []))
    const processHandle = Bun.spawn([python, "-m", "harness.verified_sidecar"], { stdin: "pipe", stdout: "pipe", stderr: "pipe", env })
    return new SidecarClient(runId, rootScopeId, processHandle, secrets)
  }

  request(type: string, payload: Record<string, unknown>, scopeId = this.rootScopeId): Promise<Record<string, any>> {
    if (this.stopped) return Promise.reject(new VerificationProtocolError("Verifier is not running", "VERIFIER_UNAVAILABLE"))
    const id = randomUUID()
    const envelope = this.secrets.redact({ version: PROTOCOL_VERSION, id, runId: this.runId, scopeId, type, payload })
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { this.pending.delete(id); reject(new VerificationProtocolError(`Verifier request timed out: ${type}`, "VERIFIER_TIMEOUT")) }, 30_000)
      this.pending.set(id, { resolve, reject, timer })
      this.processHandle.stdin.write(JSON.stringify(envelope) + "\n")
      this.processHandle.stdin.flush()
    })
  }

  open(workspace: string, source: Record<string, string>) { return this.request("run.open", { workspace, goalSources: [source] }) }
  propose(contract: Record<string, unknown>, amendment: boolean) { return this.request(amendment ? "contract.amend" : "contract.propose", { contract }) }
  openAction(payload: Record<string, unknown>) { return this.request("action.open", payload) }
  closeAction(payload: Record<string, unknown>) { return this.request("action.close", payload) }
  verify(reason = "completion") { return this.request("verify.request", { reason }) }

  async dispose(): Promise<void> {
    if (this.stopped) return
    this.stopped = true
    try { this.processHandle.stdin.end() } catch {}
    try { this.processHandle.kill() } catch {}
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(new VerificationProtocolError("Verifier stopped", "VERIFIER_STOPPED")) }
    this.pending.clear()
  }

  private async readLoop(): Promise<void> {
    const reader = this.processHandle.stdout.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      this.buffer += decoder.decode(value, { stream: true })
      for (;;) {
        const newline = this.buffer.indexOf("\n")
        if (newline < 0) break
        const line = this.buffer.slice(0, newline)
        this.buffer = this.buffer.slice(newline + 1)
        if (line.trim()) this.receive(line)
      }
    }
  }

  private receive(line: string): void {
    let response: Record<string, any>
    try { response = JSON.parse(line) } catch { this.failAll(new VerificationProtocolError("Verifier emitted malformed NDJSON")); return }
    if (response.version !== PROTOCOL_VERSION || typeof response.id !== "string") { this.failAll(new VerificationProtocolError("Verifier protocol version mismatch")); return }
    const pending = this.pending.get(response.id)
    if (!pending) return
    this.pending.delete(response.id)
    clearTimeout(pending.timer)
    if (response.type === "failure") pending.reject(new VerificationProtocolError(String(response.payload?.message ?? "Verifier failure"), String(response.payload?.failureKind ?? "VERIFIER_FAILURE")))
    else pending.resolve(response.payload ?? {})
  }

  private async watchExit(): Promise<void> {
    const code = await this.processHandle.exited
    if (!this.stopped) this.failAll(new VerificationProtocolError(`Verifier exited with code ${code}`, "VERIFIER_EXITED"))
  }

  private failAll(error: Error): void {
    this.stopped = true
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.reject(error) }
    this.pending.clear()
  }
}
