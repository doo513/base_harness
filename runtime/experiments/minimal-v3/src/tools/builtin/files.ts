import { createHash, randomUUID } from "node:crypto"
import { mkdir, readdir, rename, writeFile } from "node:fs/promises"
import { dirname, join } from "node:path"
import type { ToolRegistry } from "../registry"
import { workspacePath } from "../path-policy"
import { ToolExecutionError } from "../types"

const hash = (value: string | Uint8Array): string => createHash("sha256").update(value).digest("hex")
const clipped = (value: string, limit = 1_000_000): { text: string; truncated: boolean } => ({ text: value.slice(0, limit), truncated: value.length > limit })

async function atomicWrite(path: string, content: string): Promise<void> {
  await mkdir(dirname(path), { recursive: true })
  const temporary = join(dirname(path), `.${randomUUID()}.base-harness.tmp`)
  await writeFile(temporary, content, "utf8")
  await rename(temporary, path)
}

export function registerFileTools(registry: ToolRegistry): void {
  registry.register({
    name: "read_file", toolset: "files", effect: "read", risk: "low",
    description: "Read a UTF-8 file inside the workspace.",
    parameters: { type: "object", properties: { path: { type: "string" }, offset: { type: "number" }, limit: { type: "number" } }, required: ["path"], additionalProperties: false },
    async execute(input, context) {
      const path = workspacePath(context.workspace, String(input.path))
      const lines = (await Bun.file(path).text()).split(/\r?\n/)
      const offset = Math.max(0, Number(input.offset ?? 0))
      const limit = Math.min(4000, Math.max(1, Number(input.limit ?? 400)))
      const text = lines.slice(offset, offset + limit).map((line, index) => `${offset + index + 1}: ${line}`).join("\n")
      return { path, ...clipped(text), totalLines: lines.length }
    },
  })
  registry.register({
    name: "list_directory", toolset: "files", effect: "read", risk: "low",
    description: "List one workspace directory without recursive traversal.",
    parameters: { type: "object", properties: { path: { type: "string" } }, required: ["path"], additionalProperties: false },
    async execute(input, context) {
      const path = workspacePath(context.workspace, String(input.path))
      const entries = await readdir(path, { withFileTypes: true })
      return entries.slice(0, 1000).map((entry) => ({ name: entry.name, type: entry.isDirectory() ? "directory" : entry.isFile() ? "file" : "other" }))
    },
  })
  registry.register({
    name: "search_text", toolset: "files", effect: "read", risk: "low",
    description: "Search workspace text with ripgrep using structured arguments.",
    parameters: { type: "object", properties: { pattern: { type: "string" }, path: { type: "string" } }, required: ["pattern"], additionalProperties: false },
    async execute(input, context) {
      const path = workspacePath(context.workspace, String(input.path ?? "."))
      const child = Bun.spawn(["rg", "--line-number", "--no-heading", "--color", "never", "--hidden", "--glob", "!.git/**", String(input.pattern), path], { cwd: context.workspace, stdout: "pipe", stderr: "pipe" })
      const [stdout, stderr, code] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited])
      if (code !== 0 && code !== 1) throw new ToolExecutionError("ripgrep failed", "SEARCH_FAILED", { code, stderr: clipped(stderr, 20_000) })
      return { code, ...clipped(stdout) }
    },
  })
  registry.register({
    name: "write_file", toolset: "files", effect: "workspace_write", risk: "medium",
    description: "Atomically create or replace a UTF-8 file inside the workspace.",
    parameters: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"], additionalProperties: false },
    async execute(input, context) {
      const path = workspacePath(context.workspace, String(input.path), false)
      const before = await Bun.file(path).exists() ? hash(new Uint8Array(await Bun.file(path).arrayBuffer())) : null
      const content = String(input.content)
      await atomicWrite(path, content)
      return { path, beforeHash: before, afterHash: hash(content), bytes: Buffer.byteLength(content) }
    },
  })
  registry.register({
    name: "replace_text", toolset: "files", effect: "workspace_write", risk: "medium",
    description: "Replace one exact text occurrence in a workspace file.",
    parameters: { type: "object", properties: { path: { type: "string" }, oldText: { type: "string" }, newText: { type: "string" } }, required: ["path", "oldText", "newText"], additionalProperties: false },
    async execute(input, context) {
      const path = workspacePath(context.workspace, String(input.path))
      const content = await Bun.file(path).text()
      const oldText = String(input.oldText)
      const first = content.indexOf(oldText)
      if (first < 0) throw new ToolExecutionError("oldText was not found", "TEXT_NOT_FOUND")
      if (content.indexOf(oldText, first + oldText.length) >= 0) throw new ToolExecutionError("oldText is not unique", "TEXT_NOT_UNIQUE")
      const next = content.slice(0, first) + String(input.newText) + content.slice(first + oldText.length)
      await atomicWrite(path, next)
      return { path, beforeHash: hash(content), afterHash: hash(next) }
    },
  })
}
