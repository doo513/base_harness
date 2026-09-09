import { createHash } from "node:crypto"
import { writeAtomicSnapshot } from "@base-harness/workspace/snapshot-persistence"
import { promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"
import type { HarnessStatus } from "./contracts"

export interface RepositoryRun {
  sessionID: string
  runId: string
  workspace: string
  interrupted: boolean
}

export interface RunRepositoryOptions {
  stateDirectory?: string
  persistent?: boolean
}

const defaultRoot = () =>
  process.platform === "win32"
    ? path.join(process.env.LOCALAPPDATA ?? os.tmpdir(), "base-harness", "coordinator")
    : path.join(process.env.XDG_STATE_HOME ?? path.join(os.homedir(), ".local", "state"), "base-harness", "coordinator")

const terminal = new Set(["ready", "blocked", "interrupted", "plan_ready"])

export class RunRepository<T extends RepositoryRun> {
  readonly runs = new Map<string, T>()
  readonly scopeRoots = new Map<string, string>()
  private readonly stateDirectory: string
  private readonly persistent: boolean
  private initialized = false
  private writes = Promise.resolve()
  private readonly writeErrors = new Map<string, Error>()

  constructor(
    options: RunRepositoryOptions = {},
    private readonly snapshotWriter: typeof writeAtomicSnapshot = writeAtomicSnapshot,
  ) {
    this.stateDirectory = options.stateDirectory ?? defaultRoot()
    this.persistent = options.persistent ?? true
  }

  async initialize() {
    if (this.initialized || !this.persistent) return
    this.initialized = true
    await fs.mkdir(this.stateDirectory, { recursive: true })
    const entries = await fs.readdir(this.stateDirectory, { withFileTypes: true }).catch(() => [])
    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith(".json")) continue
      const target = path.join(this.stateDirectory, entry.name)
      try {
        const value = JSON.parse(await fs.readFile(target, "utf8")) as Record<string, unknown>
        if (!terminal.has(String(value.phase ?? ""))) {
          value.phase = "interrupted"
          value.interrupted = true
          value.updatedAt = new Date().toISOString()
          await this.atomicWrite(target, value)
        }
      } catch {
        // Corrupt historical snapshots are not trusted or resumed.
      }
    }
  }

  get(sessionID: string) {
    return this.runs.get(this.scopeRoots.get(sessionID) ?? sessionID)
  }

  set(run: T) {
    this.runs.set(run.sessionID, run)
    this.scopeRoots.set(run.sessionID, run.sessionID)
  }

  bindScope(scopeId: string, rootSessionID: string) {
    this.scopeRoots.set(scopeId, rootSessionID)
  }

  delete(run: T) {
    this.runs.delete(run.sessionID)
    for (const [scopeId, rootId] of this.scopeRoots) {
      if (rootId === run.sessionID) this.scopeRoots.delete(scopeId)
    }
  }

  async persist(status: HarnessStatus, interrupted: boolean) {
    if (!this.persistent || !status.runId) return
    const digest = createHash("sha256").update(status.goal).digest("hex")
    const body = {
      schemaVersion: "coordinator-run-v1",
      sessionID: status.sessionID,
      runId: status.runId,
      workspace: status.workspace,
      goalDigest: digest,
      executionPlan: status.executionPlan ?? null,
      revisesPlan: status.revisesPlan ?? null,
      phase: status.phase,
      outcome: status.outcome ?? null,
      verificationState: status.verificationState,
      workerCount: status.workers.length,
      activeCount: status.activeCount,
      queuedCount: status.queuedCount,
      metrics: status.metrics,
      isolation: status.isolation ?? null,
      interrupted,
      updatedAt: new Date().toISOString(),
    }
    const target = path.join(this.stateDirectory, status.runId.replace(/[^A-Za-z0-9_.-]/g, "_") + ".json")
    const operation = this.writes.then(async () => {
      const failure = this.writeErrors.get(status.runId)
      if (failure) throw failure
      try {
        await this.atomicWrite(target, body)
      } catch (error) {
        const failure = error instanceof Error ? error : new Error(String(error))
        this.writeErrors.set(status.runId, failure)
        throw failure
      }
    })
    // A failed run stays failed, without poisoning snapshots belonging to other runs.
    this.writes = operation.then(() => undefined, () => undefined)
    await operation
  }

  reset() {
    this.runs.clear()
    this.scopeRoots.clear()
    this.writeErrors.clear()
  }

  private async atomicWrite(target: string, value: unknown) {
    await this.snapshotWriter(target, JSON.stringify(value, null, 2) + "\n")
  }
}
