import { createHash, createHmac, randomBytes, randomUUID, timingSafeEqual } from "node:crypto"
import { link, lstat, mkdir, readFile, realpath, unlink, writeFile } from "node:fs/promises"
import { writeAtomicSnapshot } from "@base-harness/workspace/snapshot-persistence"
import os from "node:os"
import path from "node:path"
import type { KernelSessionState, MetaReviewReport, PlanSpec } from "@base-harness/kernel"

export interface PlanExecutionPolicy {
  configuredProfile: "fast" | "adaptive" | "strict"
  effectiveProfile: "fast" | "adaptive" | "strict"
  trigger: "auto" | "manual"
  maxSameFailureRepairs: number
  maxParallelWorkUnits: number
}

export interface PlanSelection {
  providerID: string
  modelID: string
  variant?: string
  agent: string
  messageID: string
}

export interface ReviewedPlanRecord {
  schemaVersion: "reviewed-plan-v1"
  sessionID: string
  workspace: string
  goal: string
  plan: PlanSpec
  contract: unknown
  state: KernelSessionState
  review: MetaReviewReport
  preflight?: unknown
  policy: PlanExecutionPolicy
  selection?: PlanSelection
  revisionOf?: { revision: number; digest: string }
}

export interface PlanRevisionClaim {
  record: ReviewedPlanRecord
  token: string
}

interface RevisionResolution {
  schemaVersion: "plan-revision-resolution-v1"
  sessionID: string
  planId: string
  revision: number
  previousDigest: string
  reason: "publish" | "discard"
  timestamp: string
  next?: ReviewedPlanRecord
}

export interface ReviewedPlanStoreOptions {
  directory?: string
  redact?: <T>(runId: string, value: T) => T
}

export const planDigest = (value: unknown) => createHash("sha256").update(JSON.stringify(value)).digest("hex")
const limit = 10 * 1024 * 1024
const fail: (code: string) => never = code => { throw Object.assign(new Error(code), { code }) }
const normalized = (value: string) => process.platform === "win32" ? path.resolve(value).toLowerCase() : path.resolve(value)
const within = (root: string, file: string) => normalized(file) === normalized(root)
  || normalized(file).startsWith(normalized(root) + path.sep)

export class ReviewedPlanStore {
  private readonly options: ReviewedPlanStoreOptions
  constructor(
    options: ReviewedPlanStoreOptions = {},
    private readonly snapshotWriter: typeof writeAtomicSnapshot = writeAtomicSnapshot,
  ) { this.options = options }

  private root() {
    return this.options.directory ?? path.join(process.platform === "win32"
      ? process.env.LOCALAPPDATA ?? path.join(os.homedir(), "AppData", "Local")
      : process.env.XDG_STATE_HOME ?? path.join(os.homedir(), ".local", "state"), "base-harness", "plans")
  }

  private id(value: string) {
    if (!/^[A-Za-z0-9_-]{1,128}$/.test(value)) fail("PLAN_ID_INVALID")
    return value
  }

  private async directory(id?: string, create = false) {
    const root = this.root()
    const directory = id ? path.join(root, this.id(id)) : root
    if (create) await mkdir(directory, { recursive: true, mode: 0o700 })
    if (normalized(await realpath(root)) !== normalized(root)
        || normalized(await realpath(directory)) !== normalized(directory)) fail("PLAN_STORE_PATH_INVALID")
    return directory
  }

  private async bytes(file: string) {
    const info = await lstat(file)
    if (!info.isFile() || info.isSymbolicLink() || info.size > limit
        || normalized(await realpath(file)) !== normalized(file)) fail("PLAN_STORE_PATH_INVALID")
    return readFile(file)
  }

  private async key(create: boolean) {
    const file = path.join(await this.directory(undefined, create), ".signing-key")
    if (create) {
      await writeFile(file, randomBytes(32), { flag: "wx", mode: 0o600 }).catch((error: NodeJS.ErrnoException) => {
        if (error.code !== "EEXIST") throw error
      })
    }
    const key = await this.bytes(file)
    if (key.byteLength !== 32) fail("PLAN_STORE_KEY_INVALID")
    return key
  }

  private async atomic(file: string, value: unknown) {
    const body = JSON.stringify(value, null, 2) + "\n"
    if (Buffer.byteLength(body) > limit) fail("PLAN_STORE_LIMIT_EXCEEDED")
    if (!(await this.snapshotWriter(file, body))) fail("PLAN_STORE_WRITE_INVALIDATED")
  }

  /** Publish a complete file exclusively; readers never observe a partially written decision. */
  private async exclusive(file: string, value: unknown, code = "PLAN_ALREADY_CONSUMED") {
    const body = JSON.stringify(value, null, 2) + "\n"
    if (Buffer.byteLength(body) > limit) fail("PLAN_STORE_LIMIT_EXCEEDED")
    const temporary = file + "." + randomUUID() + ".tmp"
    await writeFile(temporary, body, { flag: "wx", mode: 0o600 })
    try {
      await link(temporary, file).catch((error: NodeJS.ErrnoException) => {
        if (error.code === "EEXIST") fail(code)
        throw error
      })
    } finally {
      await unlink(temporary).catch(() => undefined)
    }
  }

  private async signed<T>(body: T, create = false) {
    const signature = createHmac("sha256", await this.key(create)).update(JSON.stringify(body)).digest("hex")
    return { body, signature }
  }

  private async verified<T>(value: unknown): Promise<T> {
    const envelope = value as { body: T; signature: string } | undefined
    if (!envelope?.body || typeof envelope.signature !== "string"
        || !/^[a-f0-9]{64}$/.test(envelope.signature)) fail("PLAN_INTEGRITY_INVALID")
    const expected = createHmac("sha256", await this.key(false)).update(JSON.stringify(envelope.body)).digest()
    if (!timingSafeEqual(Buffer.from(envelope.signature, "hex"), expected)) fail("PLAN_INTEGRITY_INVALID")
    return envelope.body
  }

  async save(record: ReviewedPlanRecord, revision?: PlanRevisionClaim): Promise<ReviewedPlanRecord> {
    const clean = this.options.redact?.(record.plan.runId, record) ?? record
    // A redacted instruction is not the instruction that was reviewed. Do not silently change it.
    if (planDigest(clean) !== planDigest(record)) fail("PLAN_SECRET_REDACTION_REQUIRED")
    const workspace = await realpath(record.workspace)
    const directory = await this.directory(record.plan.planId, true)
    if (within(workspace, directory)) fail("PLAN_STORE_INSIDE_WORKSPACE")
    const body: ReviewedPlanRecord = { ...clean, workspace }
    if (revision) {
      const previous = revision.record
      if (body.sessionID !== previous.sessionID || body.plan.planId !== previous.plan.planId
          || body.plan.revision !== previous.plan.revision + 1
          || body.plan.runId === previous.plan.runId || normalized(workspace) !== normalized(previous.workspace)) {
        fail("PLAN_REVISION_INVALID")
      }
      await this.assertCurrent(previous)
      const consumption = await this.consumption(previous)
      if (consumption?.reason !== "revise" || !revision.token || consumption.revisionToken !== revision.token) {
        fail("PLAN_REVISION_CLAIM_INVALID")
      }
      const resolution = await this.resolution(previous)
      if (resolution) fail(resolution.reason === "discard" ? "PLAN_REVISION_DISCARDED" : "PLAN_SUPERSEDED")
      body.revisionOf = { revision: previous.plan.revision, digest: planDigest(previous) }
      // One publisher per claim. A crashed publisher can be discarded, never implicitly replayed.
      await this.exclusive(path.join(directory, previous.plan.revision + ".publishing.json"),
        { token: revision.token }, "PLAN_REVISION_PUBLISHING")
    } else if (body.plan.revision !== 1 || body.revisionOf) {
      fail("PLAN_REVISION_CLAIM_REQUIRED")
    }
    const envelope = await this.signed(body, true)
    await this.atomic(path.join(directory, body.plan.revision + ".json"), body.plan)
    if (revision) {
      // The complete canonical plan precedes the single-winner publication/discard decision.
      await this.finishRevision(revision.record, "publish", body)
      // This is only a read cache. A crash before updating it is recovered via the signed decision.
      await this.atomic(path.join(directory, "reviewed.json"), envelope)
    } else {
      await this.exclusive(path.join(directory, "reviewed.json"), envelope, "PLAN_ALREADY_REVIEWED")
      const sessions = await this.directory("sessions", true)
      await this.atomic(path.join(sessions, planDigest(body.sessionID) + ".json"), { planId: body.plan.planId })
    }
    return body
  }

  /** A revision marker means pending, not proof that its producing process has exited. */
  async findPending(sessionID: string): Promise<{
    record: ReviewedPlanRecord; state: "ready" | "revision_pending"
  } | undefined> {
    const pointer = path.join(this.root(), "sessions", planDigest(sessionID) + ".json")
    try {
      await lstat(pointer)
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return
      throw error
    }
    const record = await this.readRecord({ sessionID })
    const marker = await this.consumption(record)
    if (!marker) return { record, state: "ready" }
    if (marker.reason === "revise" && !(await this.resolution(record))) {
      return { record, state: "revision_pending" }
    }
    return undefined
  }

  /** Explicit cancellation wins against publication, or rejects if a newer review already won. */
  async discardRevision(record: ReviewedPlanRecord) {
    await this.assertCurrent(record)
    if ((await this.consumption(record))?.reason !== "revise") fail("PLAN_NOT_REVISING")
    await this.finishRevision(record, "discard")
  }

  async load(input: { planId?: string; sessionID?: string }): Promise<ReviewedPlanRecord> {
    const record = await this.readRecord(input)
    await this.assertUnclaimed(record)
    return record
  }

  private async readRecord(input: { planId?: string; sessionID?: string }): Promise<ReviewedPlanRecord> {
    let planId = input.planId
    if (!planId) {
      if (!input.sessionID) fail("PLAN_ID_REQUIRED")
      const pointer = JSON.parse((await this.bytes(path.join(await this.directory("sessions"),
        planDigest(input.sessionID) + ".json"))).toString("utf8"))
      planId = pointer.planId
    }
    if (typeof planId !== "string") fail("PLAN_ID_INVALID")
    const directory = await this.directory(planId)
    let record = await this.verified<ReviewedPlanRecord>(
      JSON.parse((await this.bytes(path.join(directory, "reviewed.json"))).toString("utf8")))
    const seen = new Set<number>()
    while (true) {
      if (record?.schemaVersion !== "reviewed-plan-v1" || record.plan?.planId !== planId
          || !Number.isSafeInteger(record.plan.revision) || record.plan.revision < 1
          || record.state?.planningState !== "plan_ready" || record.review?.phase !== "plan"
          || record.review.outcome !== "pass"
          || (input.sessionID !== undefined && record.sessionID !== input.sessionID)) fail("PLAN_RECORD_INVALID")
      if (seen.has(record.plan.revision)) fail("PLAN_REVISION_INVALID")
      seen.add(record.plan.revision)
      const active = JSON.parse((await this.bytes(path.join(await this.directory("sessions"),
        planDigest(record.sessionID) + ".json"))).toString("utf8"))
      if (active.planId !== record.plan.planId) fail("PLAN_SUPERSEDED")
      const canonical = JSON.parse((await this.bytes(path.join(directory, record.plan.revision + ".json"))).toString("utf8"))
      if (planDigest(canonical) !== planDigest(record.plan)) fail("PLAN_INTEGRITY_INVALID")
      if (record.revisionOf) {
        if (record.revisionOf.revision !== record.plan.revision - 1) fail("PLAN_REVISION_INVALID")
        const parent = await this.readResolution(record, record.revisionOf.revision)
        if (parent?.reason !== "publish" || parent.previousDigest !== record.revisionOf.digest
            || planDigest(parent.next) !== planDigest(record)) fail("PLAN_INTEGRITY_INVALID")
      }
      const resolution = await this.resolution(record)
      if (!resolution || resolution.reason === "discard") return record
      if (!resolution.next || resolution.next.plan.revision !== record.plan.revision + 1
          || resolution.next.sessionID !== record.sessionID
          || resolution.next.revisionOf?.digest !== planDigest(record)) fail("PLAN_REVISION_INVALID")
      record = resolution.next
    }
  }

  private async consumption(record: ReviewedPlanRecord, revision = record.plan.revision): Promise<{
    reason: "execute" | "discard" | "revise"; timestamp: string; revisionToken?: string
  } | undefined> {
    let bytes: Buffer
    try { bytes = await this.bytes(path.join(this.root(), this.id(record.plan.planId), revision + ".consumed.json")) }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return
      throw error
    }
    const marker = JSON.parse(bytes.toString("utf8"))
    if (!["execute", "discard", "revise"].includes(marker?.reason)
        || typeof marker?.timestamp !== "string") fail("PLAN_CONSUMPTION_INVALID")
    return marker
  }

  private async readResolution(record: ReviewedPlanRecord, revision = record.plan.revision) {
    let bytes: Buffer
    try { bytes = await this.bytes(path.join(this.root(), this.id(record.plan.planId), revision + ".resolution.json")) }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return
      throw error
    }
    const result = await this.verified<RevisionResolution>(JSON.parse(bytes.toString("utf8")))
    if (result.schemaVersion !== "plan-revision-resolution-v1" || result.planId !== record.plan.planId
        || result.sessionID !== record.sessionID || result.revision !== revision
        || !["publish", "discard"].includes(result.reason) || typeof result.timestamp !== "string"
        || (await this.consumption(record, revision))?.reason !== "revise") fail("PLAN_REVISION_INVALID")
    return result
  }

  private async resolution(record: ReviewedPlanRecord) {
    const result = await this.readResolution(record)
    if (result && result.previousDigest !== planDigest(record)) fail("PLAN_INTEGRITY_INVALID")
    return result
  }

  private async assertCurrent(record: ReviewedPlanRecord) {
    const current = await this.readRecord({ sessionID: record.sessionID, planId: record.plan.planId })
    if (planDigest(current) !== planDigest(record)) fail("PLAN_SUPERSEDED")
  }

  private async finishRevision(record: ReviewedPlanRecord, reason: "publish" | "discard", next?: ReviewedPlanRecord) {
    const body: RevisionResolution = {
      schemaVersion: "plan-revision-resolution-v1", sessionID: record.sessionID,
      planId: record.plan.planId, revision: record.plan.revision, previousDigest: planDigest(record),
      reason, timestamp: new Date().toISOString(), ...(next ? { next } : {}),
    }
    try {
      await this.exclusive(path.join(this.root(), this.id(record.plan.planId), record.plan.revision + ".resolution.json"),
        await this.signed(body), "PLAN_REVISION_RESOLVED")
    } catch (error) {
      if ((error as { code?: string }).code !== "PLAN_REVISION_RESOLVED") throw error
      const existing = await this.resolution(record)
      if (reason === "discard" && existing?.reason === "discard") return
      fail(existing?.reason === "discard" ? "PLAN_REVISION_DISCARDED" : "PLAN_SUPERSEDED")
    }
  }

  private marker(record: ReviewedPlanRecord) {
    return path.join(this.root(), this.id(record.plan.planId), record.plan.revision + ".consumed.json")
  }

  async assertUnclaimed(record: ReviewedPlanRecord) {
    try {
      await lstat(this.marker(record))
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") return
      throw error
    }
    fail("PLAN_ALREADY_CONSUMED")
  }

  /** Exclusive creation also prevents another Host process from dispatching the same revision. */
  async consume(record: ReviewedPlanRecord, reason: "revise"): Promise<PlanRevisionClaim>
  async consume(record: ReviewedPlanRecord, reason: "execute" | "discard"): Promise<void>
  async consume(record: ReviewedPlanRecord, reason: "execute" | "discard" | "revise"): Promise<PlanRevisionClaim | void> {
    await this.assertCurrent(record)
    await this.directory(record.plan.planId, true)
    const revisionToken = reason === "revise" ? randomUUID() : undefined
    await this.exclusive(this.marker(record), { reason, timestamp: new Date().toISOString(), revisionToken })
    if (revisionToken) return { record, token: revisionToken }
  }
}
