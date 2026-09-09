import { describe, expect } from "bun:test"
import { $ } from "bun"
import fs from "fs/promises"
import path from "path"
import { Effect } from "effect"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import { Git } from "@base-harness/core/git"
import { AbsolutePath, RelativePath } from "@base-harness/core/schema"
import { branch, commit, gitRemote } from "./fixture/git"
import { tmpdir } from "./fixture/tmpdir"
import { testEffect } from "./lib/effect"

const it = testEffect(LayerNode.compile(Git.node))

describe("Git", () => {
  it.live("clones a remote and reads checkout metadata", () =>
    withRemote((fixture) =>
      Effect.gen(function* () {
        const git = yield* Git.Service
        const target = AbsolutePath.make(path.join(fixture.root, "checkout"))
        const repository = yield* git.repo.clone({ remote: fixture.remote, directory: target })

        expect(yield* git.remote.get(repository)).toBe(fixture.remote)
        expect(yield* git.history.head(repository)).toBeString()
        expect(yield* git.history.branch(repository)).toBe("main")
        expect(yield* git.history.defaultRemoteBranch(repository)).toBe("main")
        expect(repository.worktree).toBe(target)
        expect(repository.gitDirectory).toBe(AbsolutePath.make(path.join(target, ".git")))
        expect(repository.commonDirectory).toBe(repository.gitDirectory)
        expect(yield* read(path.join(target, "README.md"))).toBe("one\n")
      }),
    ),
  )

  it.live("fetches, checks out, and resets remote changes", () =>
    withRemote((fixture) =>
      Effect.gen(function* () {
        const git = yield* Git.Service
        const target = AbsolutePath.make(path.join(fixture.root, "checkout"))
        const repository = yield* git.repo.clone({ remote: fixture.remote, directory: target })

        yield* Effect.promise(() => commit(fixture.source, "two\n", "second"))
        yield* git.sync.fetchRemotes(repository)
        yield* git.sync.resetHard(repository, "origin/main")
        expect(yield* read(path.join(target, "README.md"))).toBe("two\n")

        yield* Effect.promise(() => branch(fixture.source, "feature/docs", "feature\n"))
        yield* git.sync.fetchBranch(repository, { branch: "feature/docs" })
        yield* git.sync.checkoutRemoteBranch(repository, { branch: "feature/docs" })
        yield* git.sync.resetHard(repository, "origin/feature/docs")
        expect(yield* git.history.branch(repository)).toBe("feature/docs")
        expect(yield* read(path.join(target, "README.md"))).toBe("feature\n")
      }),
    ),
  )
})

describe("Git discovery boundaries", () => {
  it.live("discovers from a nested directory without changing the caller's starting point", () =>
    withDiscoveryRepository((directory) => Effect.gen(function* () {
      const nested = path.join(directory, "scope", "nested")
      yield* Effect.promise(() => fs.mkdir(nested, { recursive: true }))
      const git = yield* Git.Service
      const repository = yield* git.repo.discover(AbsolutePath.make(nested))
      expect(repository?.worktree).toBe(AbsolutePath.make(directory))
      expect(repository?.gitDirectory).toBe(AbsolutePath.make(path.join(directory, ".git")))
      if (process.platform === "win32") {
        const alternate = nested.toUpperCase().split(path.sep).join("/")
        const same = yield* git.repo.discover(AbsolutePath.make(alternate))
        expect(same?.worktree.toLowerCase()).toBe(directory.toLowerCase())
      }
    })),
  )

  it.live("does not discover an ancestor repository above an explicit ceiling", () =>
    withDiscoveryRepository((directory) => Effect.gen(function* () {
      const ceiling = path.join(directory, "scope")
      const nested = path.join(ceiling, "nested")
      yield* Effect.promise(() => fs.mkdir(nested, { recursive: true }))
      const git = yield* Git.Service
      const repository = yield* withDiscoveryCeilings([ceiling], () =>
        git.repo.discover(AbsolutePath.make(nested)),
      )
      expect(repository).toBeUndefined()
    })),
  )

  it.live("excludes a ceiling ancestor but still discovers when starting at that directory", () =>
    withDiscoveryRepository((directory) => Effect.gen(function* () {
      const nested = path.join(directory, "nested")
      yield* Effect.promise(() => fs.mkdir(nested))
      const git = yield* Git.Service
      yield* withDiscoveryCeilings([directory], () => Effect.gen(function* () {
        expect(yield* git.repo.discover(AbsolutePath.make(nested))).toBeUndefined()
        expect((yield* git.repo.discover(AbsolutePath.make(directory)))?.worktree).toBe(AbsolutePath.make(directory))
      }))
    })),
  )

  it.live("keeps the nearest repository below a ceiling and ignores sibling-prefix ceilings", () =>
    withDiscoveryRepository((directory) => Effect.gen(function* () {
      const ceiling = path.join(directory, "scope")
      const inner = path.join(ceiling, "inner")
      const nested = path.join(inner, "nested")
      const sibling = path.join(directory, "sco")
      yield* Effect.promise(async () => {
        await fs.mkdir(nested, { recursive: true })
        await fs.mkdir(sibling)
        await initRepo(inner)
      })
      const git = yield* Git.Service
      yield* withDiscoveryCeilings([ceiling, sibling], () => Effect.gen(function* () {
        const repository = yield* git.repo.discover(AbsolutePath.make(nested))
        expect(repository?.worktree).toBe(AbsolutePath.make(inner))
        expect(repository?.gitDirectory).toBe(AbsolutePath.make(path.join(inner, ".git")))
      }))
    })),
  )

  it.live("discovers a linked worktree below a ceiling with its common directory outside", () =>
    withDiscoveryRepository((directory) => Effect.gen(function* () {
      const ceiling = path.join(directory, "copies")
      const linked = AbsolutePath.make(path.join(ceiling, "linked"))
      yield* Effect.promise(() => fs.mkdir(ceiling))
      const git = yield* Git.Service
      const source = yield* git.repo.discover(AbsolutePath.make(directory))
      if (!source) throw new Error("Fixture source repository not found")
      yield* git.worktree.create({ repository: source, directory: linked })
      const nested = path.join(linked, "nested")
      yield* Effect.promise(() => fs.mkdir(nested))
      yield* withDiscoveryCeilings([ceiling], () => Effect.gen(function* () {
        const repository = yield* git.repo.discover(AbsolutePath.make(nested))
        expect(repository?.worktree).toBe(linked)
        expect(repository?.commonDirectory).toBe(source.commonDirectory)
        expect(repository?.gitDirectory).not.toBe(source.gitDirectory)
      }))
      yield* git.worktree.remove({ repository: source, directory: linked, force: true })
    })),
  )

  it.live("does not advertise a bare repository as a working tree", () =>
    Effect.acquireUseRelease(
      Effect.promise(() => tmpdir()),
      (root) => Effect.gen(function* () {
        yield* Effect.promise(() => $`git init --bare`.cwd(root.path).quiet())
        const git = yield* Git.Service
        expect(yield* git.repo.discover(AbsolutePath.make(root.path))).toBeUndefined()
      }),
      (root) => Effect.promise(() => root[Symbol.asyncDispose]()),
    ),
  )
})

function withDiscoveryRepository<A, E, R>(body: (directory: string) => Effect.Effect<A, E, R>) {
  return Effect.acquireUseRelease(
    Effect.promise(() => tmpdir()),
    (root) => Effect.gen(function* () {
      yield* Effect.promise(() => initRepo(root.path))
      return yield* body(root.path)
    }),
    (root) => Effect.promise(() => root[Symbol.asyncDispose]()),
  )
}

function withDiscoveryCeilings<A, E, R>(ceilings: string[], body: () => Effect.Effect<A, E, R>) {
  return Effect.acquireUseRelease(
    Effect.sync(() => {
      const previous = process.env.GIT_CEILING_DIRECTORIES
      process.env.GIT_CEILING_DIRECTORIES = [previous, ...ceilings].filter(Boolean).join(path.delimiter)
      return previous
    }),
    body,
    (previous) => Effect.sync(() => {
      if (previous === undefined) delete process.env.GIT_CEILING_DIRECTORIES
      else process.env.GIT_CEILING_DIRECTORIES = previous
    }),
  )
}

function withRemote<A, E, R>(body: (fixture: Awaited<ReturnType<typeof gitRemote>>) => Effect.Effect<A, E, R>) {
  return Effect.acquireUseRelease(
    Effect.promise(async () => {
      const root = await tmpdir()
      return { root, fixture: await gitRemote(root.path) }
    }),
    (input) => body(input.fixture),
    (input) => Effect.promise(() => input.root[Symbol.asyncDispose]()),
  )
}

function read(file: string) {
  return Effect.promise(() => fs.readFile(file, "utf8")).pipe(Effect.map((content) => content.replace(/\r\n/g, "\n")))
}

async function initRepo(directory: string) {
  await $`git init`.cwd(directory).quiet()
  await $`git config core.fsmonitor false`.cwd(directory).quiet()
  await $`git config commit.gpgsign false`.cwd(directory).quiet()
  await $`git config user.email test@opencode.test`.cwd(directory).quiet()
  await $`git config user.name Test`.cwd(directory).quiet()
  await $`git commit --allow-empty -m root`.cwd(directory).quiet()
}

describe("Git worktrees", () => {
  it.live("creates, lists, and removes linked worktrees", () =>
    Effect.gen(function* () {
      const root = yield* Effect.acquireRelease(
        Effect.promise(() => tmpdir()),
        (dir) => Effect.promise(() => dir[Symbol.asyncDispose]()),
      )
      yield* Effect.promise(() => initRepo(root.path))
      const directory = AbsolutePath.make(yield* Effect.promise(() => fs.realpath(root.path)))
      const worktree = AbsolutePath.make(`${root.path}-git-worktree`)
      yield* Effect.addFinalizer(() =>
        Effect.promise(() => fs.rm(worktree, { recursive: true, force: true })).pipe(Effect.ignore),
      )
      const git = yield* Git.Service
      const repo = yield* git.repo.discover(directory)
      if (!repo) throw new Error("Repository not found")

      yield* git.worktree.create({ repository: repo, directory: worktree })

      expect((yield* git.worktree.list(repo)).some((entry) => entry.directory.endsWith("-git-worktree"))).toBe(true)
      const linked = yield* git.repo.discover(worktree)
      expect(linked?.worktree).toBe(AbsolutePath.make(yield* Effect.promise(() => fs.realpath(worktree))))
      expect(linked?.commonDirectory).toBe(repo.commonDirectory)
      expect(linked?.gitDirectory).not.toBe(repo.gitDirectory)
      if (!linked) throw new Error("Linked worktree not found")
      yield* git.worktree.remove({ repository: linked, directory: worktree, force: false })
      expect((yield* git.worktree.list(repo)).some((entry) => entry.directory.endsWith("-git-worktree"))).toBe(false)
    }),
  )
})

describe("Git trees", () => {
  it.live("captures, compares, previews, and restores scoped trees", () =>
    Effect.gen(function* () {
      const root = yield* Effect.acquireRelease(
        Effect.promise(() => tmpdir()),
        (dir) => Effect.promise(() => dir[Symbol.asyncDispose]()),
      )
      yield* Effect.promise(async () => {
        await initRepo(root.path)
        await fs.mkdir(path.join(root.path, "scope"))
        await fs.writeFile(path.join(root.path, "scope", "tracked.txt"), "one\n")
        await fs.writeFile(path.join(root.path, "outside.txt"), "outside\n")
        await $`git add .`.cwd(root.path).quiet()
        await $`git commit -m initial`.cwd(root.path).quiet()
      })
      const git = yield* Git.Service
      const source = yield* git.repo.discover(AbsolutePath.make(root.path))
      if (!source) throw new Error("Repository not found")
      const storage = AbsolutePath.make(path.join(root.path, ".snapshot"))
      const repository = yield* git.repo.create({ worktree: source.worktree, gitDirectory: storage, seed: source })
      yield* git.index.refresh({ repository, scope: RelativePath.make("scope") })
      const before = yield* git.tree.write(repository)

      yield* Effect.promise(async () => {
        await fs.writeFile(path.join(root.path, "scope", "tracked.txt"), "two\n")
        await fs.writeFile(path.join(root.path, "scope", "added.txt"), "added\n")
        await fs.writeFile(path.join(root.path, "outside.txt"), "changed outside\n")
      })
      yield* git.index.refresh({ repository, scope: RelativePath.make("scope") })
      const after = yield* git.tree.write(repository)

      expect(yield* git.tree.files({ repository, from: before, to: after })).toEqual([
        RelativePath.make("scope/added.txt"),
        RelativePath.make("scope/tracked.txt"),
      ])
      const diffs = yield* git.tree.diff({ repository, from: before, to: after, context: 1 })
      expect(diffs.map((item) => [item.path, item.status])).toEqual([
        [RelativePath.make("scope/added.txt"), "added"],
        [RelativePath.make("scope/tracked.txt"), "modified"],
      ])

      const files = new Map([[RelativePath.make("scope/tracked.txt"), before]])
      const preview = yield* git.tree.preview({ repository, current: after, files, context: 1 })
      expect(preview).toHaveLength(1)
      expect(preview[0]?.path).toBe(RelativePath.make("scope/tracked.txt"))
      yield* git.tree.restore({ repository, files })
      expect(yield* read(path.join(root.path, "scope", "tracked.txt"))).toBe("one\n")
      expect(yield* read(path.join(root.path, "scope", "added.txt"))).toBe("added\n")
      expect(yield* read(path.join(root.path, "outside.txt"))).toBe("changed outside\n")
    }),
  )
})
