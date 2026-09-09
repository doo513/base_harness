import { createHash, randomUUID } from "node:crypto"
import { promises as fs } from "node:fs"
import path from "node:path"

export interface CandidateFileChange {
  path: string
  before: Uint8Array | null
  after: Uint8Array
  mode: number
}

export interface CandidateTransactionOptions {
  candidateId: string
  journal: string
  validatePath(filepath: string): Promise<void>
  readCurrent(filepath: string): Promise<Uint8Array | null>
}

export type CandidateTransactionIO = Pick<typeof fs, "mkdir" | "open" | "rename" | "rm">

export class CandidateTransactionError extends Error {
  constructor(
    readonly code: "WORKSPACE_CONFLICT" | "CANDIDATE_COMMIT_FAILED" | "CANDIDATE_ROLLBACK_INCOMPLETE",
    readonly journal: string,
    readonly originalError: unknown,
    readonly recoveryFailures: Array<{ path: string; message: string }> = [],
  ) {
    super(code + ": " + (originalError instanceof Error ? originalError.message : String(originalError))
      + (recoveryFailures.length ? "; recovery journal retained at " + journal : ""))
    this.name = "CandidateTransactionError"
  }
}

const digest = (value: Uint8Array | null) =>
  value === null ? null : createHash("sha256").update(value).digest("hex")

/** Host-only filesystem transaction; it grants no verification or Ready authority. */
export async function publishCandidateFiles(
  changes: CandidateFileChange[],
  options: CandidateTransactionOptions,
  io: CandidateTransactionIO = fs,
): Promise<void> {
  const token = options.candidateId.replace(/[^A-Za-z0-9_.-]/g, "_")
  const entries = changes.map((change, index) => ({
    ...change,
    beforeHash: digest(change.before),
    afterHash: digest(change.after),
    temporary: change.path + ".base-harness-" + token + ".tmp",
    backup: change.before === null ? null : path.join(options.journal, index + ".before"),
  }))
  const applied: typeof entries = []
  const temporary = new Set<string>()
  let journalCreated = false

  const writeExclusive = async (filename: string, value: Uint8Array, mode: number, track = false) => {
    const handle = await io.open(filename, "wx", mode)
    if (track) temporary.add(filename)
    try {
      await handle.writeFile(value)
      await handle.chmod(mode)
      await handle.sync()
    } finally {
      await handle.close()
    }
  }
  const assertCurrent = async (filename: string, expected: string | null) => {
    await options.validatePath(filename)
    if (digest(await options.readCurrent(filename)) !== expected) {
      throw new CandidateTransactionError("WORKSPACE_CONFLICT", options.journal,
        new Error("Workspace changed during candidate publication: " + filename))
    }
  }
  const cleanTemporary = async () => {
    const errors: Array<{ path: string; message: string }> = []
    for (const filename of temporary) {
      try {
        await io.rm(filename, { force: true })
        temporary.delete(filename)
      } catch (error) {
        errors.push({ path: filename, message: error instanceof Error ? error.message : String(error) })
      }
    }
    return errors
  }

  try {
    await io.mkdir(path.dirname(options.journal), { recursive: true })
    await io.mkdir(options.journal)
    journalCreated = true

    // Finish all staging and durable backups before replacing the first user file.
    // Backups are copied, never renamed across workspace/state filesystem boundaries.
    for (const entry of entries) {
      await assertCurrent(entry.path, entry.beforeHash)
      await io.mkdir(path.dirname(entry.path), { recursive: true })
      await writeExclusive(entry.temporary, entry.after, entry.mode, true)
      if (entry.backup && entry.before) await writeExclusive(entry.backup, entry.before, 0o600)
    }
    await writeExclusive(path.join(options.journal, "manifest.json"), Buffer.from(JSON.stringify({
      version: 1,
      candidateId: options.candidateId,
      state: "prepared",
      files: entries.map(({ path: filename, beforeHash, afterHash, temporary, backup, mode }) =>
        ({ path: filename, beforeHash, afterHash, temporary, backup, mode })),
    }, null, 2)), 0o600)

    for (const entry of entries) {
      await assertCurrent(entry.path, entry.beforeHash)
      await assertCurrent(entry.temporary, entry.afterHash)
      await io.rename(entry.temporary, entry.path)
      temporary.delete(entry.temporary)
      applied.push(entry)
    }
    for (const entry of entries) await assertCurrent(entry.path, entry.afterHash)
    await writeExclusive(path.join(options.journal, "committed.json"), Buffer.from(JSON.stringify({
      version: 1, candidateId: options.candidateId, state: "committed",
    })), 0o600)
  } catch (error) {
    const recoveryFailures: Array<{ path: string; message: string }> = []
    for (const entry of applied.reverse()) {
      try {
        // Do not erase another writer's work while recovering our own transaction.
        await assertCurrent(entry.path, entry.afterHash)
        if (entry.before === null) {
          await io.rm(entry.path)
        } else {
          const recovery = entry.path + ".base-harness-recovery-" + randomUUID() + ".tmp"
          await writeExclusive(recovery, entry.before, entry.mode, true)
          await assertCurrent(entry.path, entry.afterHash)
          await io.rename(recovery, entry.path)
          temporary.delete(recovery)
          await assertCurrent(entry.path, entry.beforeHash)
        }
      } catch (recoveryError) {
        recoveryFailures.push({
          path: entry.path,
          message: recoveryError instanceof Error ? recoveryError.message : String(recoveryError),
        })
      }
    }
    recoveryFailures.push(...await cleanTemporary())
    if (recoveryFailures.length && journalCreated) {
      try {
        await writeExclusive(path.join(options.journal, "recovery-required.json"), Buffer.from(JSON.stringify({
          version: 1, candidateId: options.candidateId, state: "recovery_required", recoveryFailures,
        }, null, 2)), 0o600)
      } catch (journalError) {
        recoveryFailures.push({
          path: options.journal,
          message: journalError instanceof Error ? journalError.message : String(journalError),
        })
      }
    } else if (journalCreated) {
      try {
        await io.rm(options.journal, { recursive: true, force: true })
      } catch (cleanupError) {
        recoveryFailures.push({
          path: options.journal,
          message: cleanupError instanceof Error ? cleanupError.message : String(cleanupError),
        })
      }
    }
    throw new CandidateTransactionError(
      recoveryFailures.length ? "CANDIDATE_ROLLBACK_INCOMPLETE"
        : error instanceof CandidateTransactionError ? error.code : "CANDIDATE_COMMIT_FAILED",
      options.journal, error, recoveryFailures,
    )
  }

  // Cleanup failure is not a successful commit acknowledgment. Keep the committed
  // journal marker for diagnosis rather than attempting an unsafe second rollback.
  try {
    await io.rm(options.journal, { recursive: true, force: true })
  } catch (error) {
    throw new CandidateTransactionError("CANDIDATE_COMMIT_FAILED", options.journal, error)
  }
}
