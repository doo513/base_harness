import { createHash } from "node:crypto"
import { promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"

type Entry = { kind: "file" | "symlink"; hash: string }

const excluded = new Set([".git", ".venv", "node_modules", "dist", "build", ".next", "target", ".cache"])
const safeID = (value: string) => value.replace(/[^A-Za-z0-9_.-]/g, "_")
const digest = (value: Uint8Array | string) => createHash("sha256").update(value).digest("hex")

function inside(parent: string, child: string) {
  const relative = path.relative(parent, child)
  return relative === "" || (!relative.startsWith(".." + path.sep) && relative !== ".." && !path.isAbsolute(relative))
}

async function snapshot(root: string) {
  const entries = new Map<string, Entry>()
  async function visit(directory: string) {
    for (const item of await fs.readdir(directory, { withFileTypes: true })) {
      if (excluded.has(item.name)) continue
      const absolute = path.join(directory, item.name)
      const relative = path.relative(root, absolute)
      if (item.isDirectory()) {
        await visit(absolute)
        continue
      }
      if (item.isSymbolicLink()) {
        const target = await fs.realpath(absolute)
        if (!inside(root, target)) throw new Error("Managed execution rejected a link outside the workspace: " + relative)
        entries.set(relative, { kind: "symlink", hash: digest(await fs.readlink(absolute)) })
        continue
      }
      if (!item.isFile()) throw new Error("Managed execution rejected a special file: " + relative)
      entries.set(relative, { kind: "file", hash: digest(await fs.readFile(absolute)) })
    }
  }
  await visit(root)
  return entries
}

async function copyTree(source: string, destination: string, root: string) {
  const stat = await fs.lstat(source)
  if (stat.isDirectory()) {
    await fs.mkdir(destination, { recursive: true })
    for (const item of await fs.readdir(source)) {
      if (path.dirname(path.relative(root, path.join(source, item))) === "." && excluded.has(item)) continue
      await copyTree(path.join(source, item), path.join(destination, item), root)
    }
    return
  }
  if (stat.isSymbolicLink()) {
    const target = await fs.realpath(source)
    if (!inside(root, target)) throw new Error("Managed execution rejected a link outside the workspace: " + source)
    await fs.mkdir(path.dirname(destination), { recursive: true })
    await fs.symlink(await fs.readlink(source), destination)
    return
  }
  if (!stat.isFile()) throw new Error("Managed execution rejected a special file: " + source)
  await fs.mkdir(path.dirname(destination), { recursive: true })
  await fs.copyFile(source, destination)
}

export interface ManagedWorkspace {
  readonly root: string
  captureChanges(routeWrite: (relativePath: string) => Promise<{ physicalPath: string }>): Promise<string[]>
  dispose(): Promise<void>
}

export async function createManagedWorkspace(sessionID: string, workspace: string): Promise<ManagedWorkspace> {
  const source = await fs.realpath(workspace)
  const root = path.join(os.tmpdir(), "base-harness", "managed", safeID(sessionID))
  await fs.rm(root, { recursive: true, force: true })
  await copyTree(source, root, source)
  const before = await snapshot(root)
  return {
    root,
    async captureChanges(routeWrite) {
      const after = await snapshot(root)
      const changed: string[] = []
      for (const [relative, entry] of before) {
        const current = after.get(relative)
        if (!current) throw new Error("Managed execution does not support deleting workspace files: " + relative)
        if (current.kind !== entry.kind || current.hash !== entry.hash) {
          if (current.kind !== "file") throw new Error("Managed execution changed a link: " + relative)
          const route = await routeWrite(relative)
          await fs.copyFile(path.join(root, relative), route.physicalPath)
          changed.push(relative)
        }
      }
      for (const [relative, entry] of after) {
        if (before.has(relative)) continue
        if (entry.kind !== "file") throw new Error("Managed execution created a link: " + relative)
        const route = await routeWrite(relative)
        await fs.copyFile(path.join(root, relative), route.physicalPath)
        changed.push(relative)
      }
      return changed.sort()
    },
    async dispose() {
      await fs.rm(root, { recursive: true, force: true })
    },
  }
}

