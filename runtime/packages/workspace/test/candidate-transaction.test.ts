import { expect, test } from "bun:test"
import { promises as fs } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import {
  publishCandidateFiles, type CandidateFileChange, type CandidateTransactionIO,
  type CandidateTransactionOptions,
} from "../src/candidate-transaction"

async function fixture(action: (value: {
  workspace: string; state: string; changes: CandidateFileChange[];
  options: CandidateTransactionOptions; rename: CandidateTransactionIO["rename"];
  renames: Array<[string, string]>;
}) => Promise<void>) {
  const directory = await fs.mkdtemp(path.join(tmpdir(), "harness-candidate-transaction-"))
  const workspace = path.join(directory, "workspace")
  const state = path.join(directory, "state")
  await fs.mkdir(workspace)
  await fs.mkdir(state)
  const changes: CandidateFileChange[] = ["a.txt", "b.txt", "c.txt"].map((name, index) => ({
    path: path.join(workspace, name),
    before: index === 1 ? null : Buffer.from("before-" + name),
    after: Buffer.from("after-" + name),
    mode: 0o600,
  }))
  for (const entry of changes) if (entry.before) await fs.writeFile(entry.path, entry.before)
  const options: CandidateTransactionOptions = {
    candidateId: "candidate-1", journal: path.join(state, "journals", "candidate-1"),
    validatePath: async filename => {
      const relative = path.relative(workspace, filename)
      if (relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("outside workspace")
    },
    readCurrent: async filename => {
      try { return await fs.readFile(filename) }
      catch (error) { if ((error as NodeJS.ErrnoException).code === "ENOENT") return null; throw error }
    },
  }
  const renames: Array<[string, string]> = []
  const rename: CandidateTransactionIO["rename"] = async (source, target) => {
    const from = String(source), to = String(target)
    const layer = (filename: string) => filename.startsWith(workspace + path.sep) ? "workspace" : "state"
    // Enforce the cross-device constraint without requiring a second physical disk.
    if (layer(from) !== layer(to)) throw Object.assign(new Error("cross-device rename"), { code: "EXDEV" })
    renames.push([from, to])
    await fs.rename(source, target)
  }
  try {
    await action({ workspace, state, changes, options, rename, renames })
  } finally {
    const relative = path.relative(tmpdir(), directory)
    expect(relative.startsWith("..") || path.isAbsolute(relative)).toBe(false)
    await fs.rm(directory, { recursive: true, force: true })
  }
}

test("publication copies backups and keeps every atomic rename on the workspace filesystem", async () => {
  await fixture(async ({ changes, options, rename, renames }) => {
    await publishCandidateFiles(changes, options, { ...fs, rename })
    for (const entry of changes) expect(await fs.readFile(entry.path)).toEqual(Buffer.from(entry.after))
    expect(renames).toHaveLength(3)
    expect(await fs.stat(options.journal).catch(() => null)).toBeNull()
  })
})

test("a late publication failure restores original files and removes only its new file", async () => {
  await fixture(async ({ changes, options, rename }) => {
    const injected: CandidateTransactionIO["rename"] = async (source, target) => {
      if (String(target) === changes[2]!.path && String(source).endsWith(".base-harness-candidate-1.tmp")) {
        throw Object.assign(new Error("injected publication failure"), { code: "EIO" })
      }
      await rename(source, target)
    }
    const error = await publishCandidateFiles(changes, options, { ...fs, rename: injected }).catch(error => error)
    expect(error).toMatchObject({ code: "CANDIDATE_COMMIT_FAILED", recoveryFailures: [] })
    for (const entry of changes) expect(await options.readCurrent(entry.path)).toEqual(entry.before)
    expect(await fs.stat(options.journal).catch(() => null)).toBeNull()
  })
})

for (const externalWrite of [false, true]) {
  test("failed rollback retains backups and " + (externalWrite ? "preserves external changes" : "reports recovery failures"), async () => {
    await fixture(async ({ changes, options, rename }) => {
      const injected: CandidateTransactionIO["rename"] = async (source, target) => {
        const from = String(source), to = String(target)
        if (to === changes[2]!.path && from.endsWith(".base-harness-candidate-1.tmp")) {
          if (externalWrite) await fs.writeFile(changes[0]!.path, "external work")
          throw Object.assign(new Error("injected publication failure"), { code: "EIO" })
        }
        if (!externalWrite && from.includes(".base-harness-recovery-") && to === changes[0]!.path) {
          throw Object.assign(new Error("injected rollback failure"), { code: "EACCES" })
        }
        await rename(source, target)
      }
      const error = await publishCandidateFiles(changes, options, { ...fs, rename: injected }).catch(error => error)
      expect(error).toMatchObject({ code: "CANDIDATE_ROLLBACK_INCOMPLETE", journal: options.journal })
      expect(error.recoveryFailures).toHaveLength(1)
      expect(await fs.readFile(changes[0]!.path, "utf8")).toBe(externalWrite ? "external work" : "after-a.txt")
      expect(await options.readCurrent(changes[1]!.path)).toBeNull()
      expect(await fs.readFile(changes[2]!.path)).toEqual(Buffer.from(changes[2]!.before!))
      expect(await fs.readFile(path.join(options.journal, "0.before"))).toEqual(Buffer.from(changes[0]!.before!))
      const report = JSON.parse(await fs.readFile(path.join(options.journal, "recovery-required.json"), "utf8"))
      expect(report.state).toBe("recovery_required")
      expect(report.recoveryFailures[0].path).toBe(changes[0]!.path)
      expect(JSON.parse(await fs.readFile(path.join(options.journal, "manifest.json"), "utf8")).files).toHaveLength(3)
    })
  })
}

test("a preexisting staging file is not overwritten or deleted and no user file is published", async () => {
  await fixture(async ({ changes, options, rename }) => {
    const staging = changes[2]!.path + ".base-harness-candidate-1.tmp"
    await fs.writeFile(staging, "external staging")
    const error = await publishCandidateFiles(changes, options, { ...fs, rename }).catch(error => error)
    expect(error).toMatchObject({ code: "CANDIDATE_COMMIT_FAILED", recoveryFailures: [] })
    for (const entry of changes) expect(await options.readCurrent(entry.path)).toEqual(entry.before)
    expect(await fs.readFile(staging, "utf8")).toBe("external staging")
  })
})

test("staged bytes changed before publication are rejected and preceding files are restored", async () => {
  await fixture(async ({ changes, options, rename }) => {
    const injected: CandidateTransactionIO["rename"] = async (source, target) => {
      await rename(source, target)
      if (String(target) === changes[0]!.path) {
        await fs.writeFile(changes[1]!.path + ".base-harness-candidate-1.tmp", "tampered")
      }
    }
    const error = await publishCandidateFiles(changes, options, { ...fs, rename: injected }).catch(error => error)
    expect(error).toMatchObject({ code: "WORKSPACE_CONFLICT", recoveryFailures: [] })
    for (const entry of changes) expect(await options.readCurrent(entry.path)).toEqual(entry.before)
  })
})

test.skipIf(process.platform === "win32")("publication preserves executable mode on existing POSIX files", async () => {
  await fixture(async ({ changes, options, rename }) => {
    changes[0]!.mode = 0o755
    await fs.chmod(changes[0]!.path, 0o755)
    await publishCandidateFiles(changes, options, { ...fs, rename })
    expect((await fs.stat(changes[0]!.path)).mode & 0o777).toBe(0o755)
  })
})
