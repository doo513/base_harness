import { createHmac, randomBytes, randomUUID, timingSafeEqual } from "node:crypto"
import { link, lstat, mkdir, readFile, realpath, unlink, writeFile } from "node:fs/promises"
import { writeAtomicSnapshot } from "@base-harness/workspace/snapshot-persistence"
import type { KernelSessionState } from "@base-harness/kernel"
import os from "node:os"
import path from "node:path"

export type SessionSelection = Pick<KernelSessionState, "domain" | "skills" | "planningPreference" | "execution">

export interface RunHistory {
  runId: string
  recordedAt: string
  recordedPhase: string
  phase: string
  readOnly: true
  revalidated: false
  goal: string
  goalTruncated: boolean
  workers: Array<{ workUnitId: string; title: string; state: string; repairCount: number }>
  evidenceCount: number
  candidateCount: number
  evidenceRefs: string[]
  candidateRefs: string[]
  referencesTruncated: boolean
  repairCount: number
  assuranceLevel?: "fast" | "adaptive" | "strict"
}

interface SessionSnapshot {
  schemaVersion: "host-session-v1"
  sessionID: string
  workspace: string
  selection: SessionSelection
  lastRun?: RunHistory
}

export interface SessionStateStoreOptions {
  directory?: string
  redact?: <T>(runId: string, value: T) => T
}

const limit = 1024 * 1024
const fail: (code: string) => never = code => { throw Object.assign(new Error(code), { code }) }
const normal = (value: string) => process.platform === "win32" ? path.resolve(value).toLowerCase() : path.resolve(value)
const inside = (root: string, file: string) => normal(root) === normal(file)
  || normal(file).startsWith(normal(root) + path.sep)
const object = (value: unknown): value is Record<string, any> =>
  value !== null && typeof value === "object" && !Array.isArray(value)
const count = (value: unknown) => typeof value === "number" && Number.isSafeInteger(value) && value >= 0
const text = (value: unknown, max = 4096): value is string => typeof value === "string" && value.length <= max
const id = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(value)
const exactKeys = (value: Record<string, any>, allowed: string[]) =>
  Object.keys(value).every(key => allowed.includes(key))
const phaseName = (value: unknown) => text(value, 64) && /^[a-z_]+$/.test(value)
const terminal = new Set(["ready", "blocked", "failure", "interrupted", "plan_ready"])

function validSelection(value: unknown): value is SessionSelection {
  if (!object(value) || !exactKeys(value, ["domain", "skills", "planningPreference", "execution"])
      || !["develop", "general"].includes(value.domain)
      || !["auto", "plan_once"].includes(value.planningPreference)
      || !Array.isArray(value.skills) || value.skills.length > 1
      || value.skills.some((skill: unknown) => skill !== "hackathon")
      || (value.domain === "general" && value.skills.length > 0)) return false
  const execution = value.execution
  if (execution === undefined) return true
  if (!object(execution) || !exactKeys(execution, ["adapterID", "modelID", "options", "capabilityRevision"])
      || !text(execution.adapterID, 256) || !execution.adapterID
      || (execution.modelID !== undefined && !text(execution.modelID, 512))
      || (execution.capabilityRevision !== undefined && !text(execution.capabilityRevision, 512))) return false
  return execution.options === undefined || (object(execution.options)
    && Object.keys(execution.options).length <= 32
    && Object.entries(execution.options).every(([key, value]) =>
      text(key, 128) && !["__proto__", "prototype", "constructor"].includes(key) && text(value, 1024)))
}

export function sessionSelection(state: KernelSessionState): SessionSelection {
  const value = structuredClone({
    domain: state.domain, skills: state.skills, planningPreference: state.planningPreference,
    ...(state.execution ? { execution: state.execution } : {}),
  })
  if (!validSelection(value)) fail("SESSION_SELECTION_INVALID")
  return value
}

function validHistory(value: unknown): value is RunHistory {
  return object(value)
    && exactKeys(value, ["runId", "recordedAt", "recordedPhase", "phase", "readOnly", "revalidated",
      "goal", "goalTruncated", "workers", "evidenceCount", "candidateCount", "evidenceRefs",
      "candidateRefs", "referencesTruncated", "repairCount", "assuranceLevel"])
    && id(value.runId) && text(value.recordedAt, 64) && Number.isFinite(Date.parse(value.recordedAt))
    && phaseName(value.recordedPhase) && value.phase === (terminal.has(value.recordedPhase) ? value.recordedPhase : "interrupted")
    && value.readOnly === true && value.revalidated === false && text(value.goal, 16384)
    && typeof value.goalTruncated === "boolean" && typeof value.referencesTruncated === "boolean"
    && count(value.evidenceCount) && count(value.candidateCount) && count(value.repairCount)
    && (value.assuranceLevel === undefined || ["fast", "adaptive", "strict"].includes(value.assuranceLevel))
    && [value.evidenceRefs, value.candidateRefs].every(refs =>
      Array.isArray(refs) && refs.length <= 32 && refs.every(ref => text(ref, 2048)))
    && Array.isArray(value.workers) && value.workers.length <= 64
    && value.workers.every(worker => object(worker)
      && exactKeys(worker, ["workUnitId", "title", "state", "repairCount"])
      && text(worker.workUnitId, 128) && text(worker.title, 512) && text(worker.state, 64) && count(worker.repairCount))
}

/** Bounded presentation data only. No contract, plan capability, attestation or Ready authority. */
export function summarizeRun(status: any): RunHistory {
  const recordedPhase = status.planningState === "plan_ready" ? "plan_ready" : status.phase
  const refs = (values: unknown) => Array.isArray(values)
    ? values.filter((value): value is string => typeof value === "string") : []
  const evidence = refs(status.evidenceRefs), candidates = refs(status.candidateRefs)
  const value: RunHistory = {
    runId: status.runId, recordedAt: new Date().toISOString(), recordedPhase,
    phase: terminal.has(recordedPhase) ? recordedPhase : "interrupted",
    readOnly: true, revalidated: false,
    goal: String(status.goal ?? "").slice(0, 16384),
    goalTruncated: String(status.goal ?? "").length > 16384,
    workers: (status.workers ?? []).map((worker: any) => ({
      workUnitId: worker.workUnitId, title: String(worker.title ?? "").slice(0, 512),
      state: worker.state, repairCount: worker.repairCount ?? 0,
    })),
    evidenceCount: status.evidenceCount ?? 0, candidateCount: status.candidateCount ?? 0,
    evidenceRefs: evidence.filter(ref => ref.length <= 2048).slice(0, 32),
    candidateRefs: candidates.filter(ref => ref.length <= 2048).slice(0, 32),
    referencesTruncated: evidence.length > 32 || candidates.length > 32
      || [...evidence, ...candidates].some(ref => ref.length > 2048),
    repairCount: status.repairCount ?? 0,
    ...(status.assuranceLevel ? { assuranceLevel: status.assuranceLevel } : {}),
  }
  if (!validHistory(value)) fail("SESSION_HISTORY_INVALID")
  return value
}

/** Host-private selection and history. The signature is not an OS sandbox or an Evidence attestation. */
export class SessionStateStore {
  private readonly writes = new Map<string, Promise<void>>()
  constructor(
    private readonly options: SessionStateStoreOptions = {},
    private readonly writer: typeof writeAtomicSnapshot = writeAtomicSnapshot,
  ) {}

  private root() {
    return path.resolve(this.options.directory ?? path.join(process.platform === "win32"
      ? process.env.LOCALAPPDATA ?? path.join(os.homedir(), "AppData", "Local")
      : process.env.XDG_STATE_HOME ?? path.join(os.homedir(), ".local", "state"), "base-harness", "sessions"))
  }

  private async directory(workspace?: string, create = false) {
    const root = this.root()
    let ancestor = root
    for (;;) {
      try {
        const resolved = await realpath(ancestor)
        if (normal(resolved) !== normal(ancestor) || (workspace && inside(workspace, resolved))) {
          fail("SESSION_STORE_PATH_INVALID")
        }
        break
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error
        const parent = path.dirname(ancestor)
        if (parent === ancestor) throw error
        ancestor = parent
      }
    }
    if (workspace && inside(workspace, root)) fail("SESSION_STORE_PATH_INVALID")
    if (create) await mkdir(root, { recursive: true, mode: 0o700 })
    const info = await lstat(root)
    if (!info.isDirectory() || info.isSymbolicLink() || normal(await realpath(root)) !== normal(root)) {
      fail("SESSION_STORE_PATH_INVALID")
    }
    return root
  }

  private async bytes(file: string) {
    const info = await lstat(file)
    if (!info.isFile() || info.isSymbolicLink() || info.size > limit
        || normal(await realpath(file)) !== normal(file)) fail("SESSION_STORE_PATH_INVALID")
    const bytes = await readFile(file)
    if (bytes.length > limit) fail("SESSION_STORE_LIMIT_EXCEEDED")
    return bytes
  }

  private async key(root: string, create: boolean) {
    const destination = path.join(root, ".signing-key")
    if (create) {
      const temporary = destination + "." + randomUUID() + ".tmp"
      await writeFile(temporary, randomBytes(32), { flag: "wx", mode: 0o600 })
      try {
        await link(temporary, destination).catch((error: NodeJS.ErrnoException) => {
          if (error.code !== "EEXIST") throw error
        })
      } finally {
        await unlink(temporary).catch(() => undefined)
      }
    }
    const key = await this.bytes(destination).catch(() => fail("SESSION_STORE_KEY_INVALID"))
    if (key.length !== 32) fail("SESSION_STORE_KEY_INVALID")
    return key
  }

  async load(sessionID: string, workspace?: string): Promise<SessionSnapshot | undefined> {
    if (!id(sessionID)) fail("SESSION_ID_INVALID")
    await this.writes.get(sessionID)
    const expectedWorkspace = workspace ? await realpath(workspace) : undefined
    let root: string, raw: Buffer
    try {
      root = await this.directory(expectedWorkspace)
      raw = await this.bytes(path.join(root, sessionID + ".json"))
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return
      throw error
    }
    let envelope: any
    try { envelope = JSON.parse(raw.toString("utf8")) } catch { fail("SESSION_INTEGRITY_INVALID") }
    if (!object(envelope) || !object(envelope.body) || !/^[a-f0-9]{64}$/.test(envelope.signature ?? "")) {
      fail("SESSION_INTEGRITY_INVALID")
    }
    const expected = createHmac("sha256", await this.key(root, false)).update(JSON.stringify(envelope.body)).digest()
    if (!timingSafeEqual(expected, Buffer.from(envelope.signature, "hex"))) fail("SESSION_INTEGRITY_INVALID")
    const saved = envelope.body as SessionSnapshot
    if (saved.schemaVersion !== "host-session-v1" || saved.sessionID !== sessionID || !text(saved.workspace)
        || !validSelection(saved.selection) || (saved.lastRun !== undefined && !validHistory(saved.lastRun))) {
      fail("SESSION_INTEGRITY_INVALID")
    }
    const originalWorkspace = await realpath(saved.workspace)
    if ((expectedWorkspace && normal(expectedWorkspace) !== normal(originalWorkspace))
        || inside(originalWorkspace, root)) fail("SESSION_WORKSPACE_MISMATCH")
    return structuredClone(saved)
  }

  async save(input: Omit<SessionSnapshot, "schemaVersion">) {
    if (!id(input.sessionID)) fail("SESSION_ID_INVALID")
    const captured = structuredClone(input)
    const prior = this.writes.get(input.sessionID) ?? Promise.resolve()
    const write = prior.catch(() => undefined).then(async () => {
      if (!validSelection(captured.selection)
          || (captured.lastRun !== undefined && !validHistory(captured.lastRun))) fail("SESSION_HISTORY_INVALID")
      const workspace = await realpath(captured.workspace)
      const root = await this.directory(workspace, true)
      const original: SessionSnapshot = { schemaVersion: "host-session-v1", ...captured, workspace }
      const body = this.options.redact?.(captured.lastRun?.runId ?? "session-" + captured.sessionID, original) ?? original
      // Redaction must never silently change identity or permission-bearing selection.
      if (body.sessionID !== original.sessionID || body.workspace !== original.workspace
          || JSON.stringify(body.selection) !== JSON.stringify(original.selection)
          || !validSelection(body.selection) || (body.lastRun !== undefined && !validHistory(body.lastRun))) {
        fail("SESSION_REDACTION_INVALID")
      }
      const signature = createHmac("sha256", await this.key(root, true)).update(JSON.stringify(body)).digest("hex")
      const serialized = JSON.stringify({ body, signature }, null, 2) + "\n"
      if (Buffer.byteLength(serialized) > limit) fail("SESSION_STORE_LIMIT_EXCEEDED")
      if (!(await this.writer(path.join(root, captured.sessionID + ".json"), serialized))) {
        fail("SESSION_STORE_WRITE_INVALIDATED")
      }
    })
    this.writes.set(input.sessionID, write)
    try { await write } finally {
      if (this.writes.get(input.sessionID) === write) this.writes.delete(input.sessionID)
    }
  }
}
