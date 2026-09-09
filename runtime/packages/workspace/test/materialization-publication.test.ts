import { expect, spyOn, test } from "bun:test"
import { promises as fs } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import * as Workspace from "../src/orchestration"

const deferred = () => {
  let resolve!: () => void
  return { promise: new Promise<void>(done => { resolve = done }), resolve: () => resolve() }
}
const waitFor = (promise: Promise<void>) => new Promise<void>((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("Fixture barrier was not reached")), 5000)
  promise.then(() => { clearTimeout(timer); resolve() }, error => { clearTimeout(timer); reject(error) })
})
const samePath = (left: unknown, right: string) => process.platform === "win32"
  ? String(left).toLowerCase() === right.toLowerCase() : String(left) === right
const attestation = (candidate: Workspace.CandidateManifest) => ({
  candidateId: candidate.candidateId, candidateRevision: candidate.revision, patchHash: candidate.patchHash,
})

async function fixture(action: (value: {
  workspace: string; a: Workspace.CandidateManifest; b: Workspace.CandidateManifest;
}) => Promise<void>) {
  const directory = await fs.mkdtemp(path.join(tmpdir(), "harness-publication-lock-"))
  const workspace = path.join(directory, "workspace")
  const state = path.join(directory, "state")
  await fs.mkdir(workspace)
  const store = new Workspace.WorkspaceCandidateStore()
  await Workspace.withWorkspaceCandidateStore(store, async () => {
    const local = process.env.LOCALAPPDATA, xdg = process.env.XDG_STATE_HOME
    try {
      process.env.LOCALAPPDATA = state
      process.env.XDG_STATE_HOME = state
      Workspace.beginPrompt({ sessionID: "root", workspace, goal: "Update two independent files", exploration: "manual" })
      Workspace.setRunIdentity("root", "publication-lock")
    } finally {
      if (local === undefined) delete process.env.LOCALAPPDATA
      else process.env.LOCALAPPDATA = local
      if (xdg === undefined) delete process.env.XDG_STATE_HOME
      else process.env.XDG_STATE_HOME = xdg
    }
    try {
      for (const name of ["a", "b"]) await fs.writeFile(path.join(workspace, name + ".txt"), "before")
      Workspace.registerContract("root", ["claim-a", "claim-b"], ["criterion-a", "criterion-b"])
      Workspace.beginPlanning("root")
      await Workspace.acceptWorkGraph("root", {
        units: ["a", "b"].map(id => ({
          id, title: id, instructions: "Write after", claimIds: ["claim-" + id], criterionIds: ["criterion-" + id],
          dependsOn: [], readSet: [id + ".txt"], writeSet: [id + ".txt"], integrationRequests: [],
        })), integrationPaths: [],
      })
      const prepared: Workspace.CandidateManifest[] = []
      for (const id of ["a", "b"]) {
        Workspace.startChild({ parentSessionID: "root", sessionID: "worker-" + id, subagentType: "general", workUnitId: id })
        const route = await Workspace.resolveWrite("worker-" + id, workspace, id + ".txt")
        await fs.writeFile(route.physicalPath, "after")
        prepared.push((await Workspace.finishChild("worker-" + id, true))!)
      }
      const a = prepared[0]!, b = prepared[1]!
      await Workspace.materializeCandidate(a.candidateId)
      await action({ workspace, a, b })
    } finally {
      await store.commitQueue
      await store.flushPersistence()
      store.clear()
      const relative = path.relative(tmpdir(), directory)
      expect(relative.startsWith("..") || path.isAbsolute(relative)).toBe(false)
      await fs.rm(directory, { recursive: true, force: true })
    }
  })
}

for (const first of ["commit", "materialize"] as const) {
  test("candidate " + first + " excludes overlapping workspace copy/publication", async () => {
    await fixture(async ({ workspace, a, b }) => {
      const entered = deferred(), release = deferred()
      const rename = fs.rename.bind(fs), copy = fs.cp.bind(fs)
      const jobs: Promise<unknown>[] = []
      let copyStarted = false, renameStarted = false
      const renameSpy = spyOn(fs, "rename").mockImplementation(async (source, target) => {
        if (samePath(target, path.join(workspace, "a.txt"))) {
          renameStarted = true
          if (first === "commit") { entered.resolve(); await release.promise }
        }
        return rename(source, target)
      })
      const copySpy = spyOn(fs, "cp").mockImplementation(async (source, target, options) => {
        if (samePath(source, workspace)) {
          copyStarted = true
          if (first === "materialize") { entered.resolve(); await release.promise }
        }
        return copy(source, target, options)
      })
      const track = (job: Promise<unknown>) => { jobs.push(job); void job.catch(() => undefined); return job }
      try {
        const leading = track(first === "commit"
          ? Workspace.commitCandidate(a.candidateId, attestation(a))
          : Workspace.materializeCandidate(b.candidateId))
        await waitFor(entered.promise)
        const following = track(first === "commit"
          ? Workspace.materializeCandidate(b.candidateId)
          : Workspace.commitCandidate(a.candidateId, attestation(a)))
        await Bun.sleep(25)
        expect(first === "commit" ? copyStarted : renameStarted).toBe(false)
        release.resolve()
        await Promise.all([leading, following])
        expect(copyStarted && renameStarted).toBe(true)
        expect(await fs.readFile(path.join(workspace, "a.txt"), "utf8")).toBe("after")
        expect(await fs.readFile(path.join(workspace, "b.txt"), "utf8")).toBe("before")
      } finally {
        release.resolve()
        await Promise.allSettled(jobs)
        copySpy.mockRestore()
        renameSpy.mockRestore()
      }
    })
  })
}

for (const code of ["EACCES", "ENOENT"] as const) {
  test("typed copy failure " + code + " releases the queue without becoming a verifier failure", async () => {
    await fixture(async ({ workspace, a, b }) => {
      const copy = fs.cp.bind(fs)
      let injected = false
      const spy = spyOn(fs, "cp").mockImplementation(async (source, target, options) => {
        if (!injected && samePath(source, workspace)) {
          injected = true
          throw Object.assign(new Error("injected filesystem fault"), { code })
        }
        return copy(source, target, options)
      })
      try {
        const error = await Workspace.materializeCandidate(b.candidateId).catch(error => error)
        expect(error).toMatchObject({
          code: code === "ENOENT" ? "WORKSPACE_CONFLICT" : "CANDIDATE_MATERIALIZATION_FAILED",
        })
        const result = await Workspace.commitCandidate(a.candidateId, attestation(a))
        expect(result.scopeVerified).toBe(true)
        expect(await fs.readFile(path.join(workspace, "a.txt"), "utf8")).toBe("after")
      } finally {
        spy.mockRestore()
      }
    })
  })
}
