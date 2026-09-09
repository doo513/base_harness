import fs from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"

export interface SymlinkCapability {
  supported: boolean
  reason?: string
}

export function unavailableSymlinkReason(error: unknown, platform: string): string | undefined {
  if (platform !== "win32" || !error || typeof error !== "object" || !("code" in error)) return
  const code = error.code
  if (code === "EPERM" || code === "EACCES") return "Windows symlink creation denied (" + code + ")"
}

export function requireSymlinkCapabilities(
  capabilities: { file: SymlinkCapability; directory: SymlinkCapability },
  required: boolean,
) {
  if (!required || (capabilities.file.supported && capabilities.directory.supported)) return
  throw new Error(
    "SYMLINK_CAPABILITY_REQUIRED: native file and directory symlink tests cannot run. "
    + "Use a Windows environment with symlink creation enabled or a supported Linux runner. "
    + "Skipped capability checks are not validation evidence.",
  )
}

export async function probeSymlinkCapabilities() {
  const directory = await fs.mkdtemp(path.join(tmpdir(), "base-harness-symlink-probe-"))
  try {
    const file = path.join(directory, "target.txt")
    const folder = path.join(directory, "target-dir")
    await fs.writeFile(file, "capability probe")
    await fs.mkdir(folder)
    const probe = async (target: string, name: string, type: "file" | "dir"): Promise<SymlinkCapability> => {
      try {
        const link = path.join(directory, name)
        await fs.symlink(target, link, type)
        if (!(await fs.lstat(link)).isSymbolicLink()) throw new Error("SYMLINK_PROBE_INVALID: link is not symbolic")
        return { supported: true }
      } catch (error) {
        const reason = unavailableSymlinkReason(error, process.platform)
        if (!reason) throw error
        return { supported: false, reason }
      }
    }
    return { file: await probe(file, "file-link", "file"), directory: await probe(folder, "dir-link", "dir") }
  } finally {
    const relative = path.relative(tmpdir(), directory)
    if (!relative || relative.startsWith("..") || path.isAbsolute(relative)) throw new Error("Unsafe probe cleanup")
    await fs.rm(directory, { recursive: true, force: true, maxRetries: 3, retryDelay: 100 })
  }
}
