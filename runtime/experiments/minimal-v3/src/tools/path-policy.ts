import { existsSync, lstatSync, realpathSync } from "node:fs"
import { dirname, isAbsolute, relative, resolve } from "node:path"
import { ToolExecutionError } from "./types"

const canonical = (value: string): string => process.platform === "win32" ? value.toLowerCase() : value

function inside(root: string, target: string): boolean {
  const rel = relative(canonical(root), canonical(target))
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel))
}

export function workspacePath(workspace: string, input: string, mustExist = true): string {
  if (!input || input.includes("\0")) throw new ToolExecutionError("Invalid workspace path", "INVALID_PATH")
  const root = realpathSync(resolve(workspace))
  const requested = resolve(root, input)
  let probe = requested
  while (!existsSync(probe)) {
    const parent = dirname(probe)
    if (parent === probe) break
    probe = parent
  }
  const realProbe = realpathSync(probe)
  if (!inside(root, realProbe) || !inside(root, requested)) throw new ToolExecutionError("Path escapes the workspace", "WORKSPACE_ESCAPE")
  if (mustExist && !existsSync(requested)) throw new ToolExecutionError(`Path does not exist: ${input}`, "PATH_NOT_FOUND")
  if (existsSync(requested)) {
    const realTarget = realpathSync(requested)
    if (!inside(root, realTarget)) throw new ToolExecutionError("Symlink target escapes the workspace", "WORKSPACE_ESCAPE")
    const stat = lstatSync(requested)
    if (stat.isSocket() || stat.isFIFO() || stat.isBlockDevice() || stat.isCharacterDevice()) throw new ToolExecutionError("Special files are not allowed", "SPECIAL_FILE_DENIED")
    return realTarget
  }
  return requested
}
