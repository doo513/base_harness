import { existsSync } from "node:fs"
import { readdir } from "node:fs/promises"
import { homedir } from "node:os"
import { basename, join } from "node:path"

export interface Skill { name: string; path: string; content: string }

export async function loadSkills(workspace: string, extraPaths: string[]): Promise<Map<string, Skill>> {
  const roots = [join(workspace, ".base-harness", "skills"), join(homedir(), ".base-harness", "skills"), ...extraPaths]
  const result = new Map<string, Skill>()
  for (const root of roots) {
    if (!existsSync(root)) continue
    for (const entry of await readdir(root, { withFileTypes: true })) {
      const path = entry.isDirectory() ? join(root, entry.name, "SKILL.md") : entry.name.endsWith(".md") ? join(root, entry.name) : ""
      if (!path || !existsSync(path)) continue
      const content = (await Bun.file(path).text()).slice(0, 64_000)
      const frontmatter = content.match(/^---\s*[\r\n]+([\s\S]*?)[\r\n]+---/)
      const declared = frontmatter?.[1].match(/^name:\s*(.+)$/m)?.[1]?.trim()
      const name = declared || (entry.isDirectory() ? entry.name : basename(entry.name, ".md"))
      result.set(name, { name, path, content })
    }
  }
  return result
}
