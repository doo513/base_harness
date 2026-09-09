import { randomUUID } from "node:crypto"
import { promises as fs } from "node:fs"
import path from "node:path"
import { setTimeout as delay } from "node:timers/promises"

const windowsRetryDelays = [10, 25, 50, 100, 200] as const
const windowsRetryCodes = new Set(["EPERM", "EACCES", "EBUSY"])

export interface SnapshotPersistenceOptions {
  isCurrent?: () => boolean
  platform?: NodeJS.Platform
  rename?: (source: string, destination: string) => Promise<void>
  sleep?: (milliseconds: number) => Promise<void>
}

/** Replace only via a same-directory rename. Never unlink or copy over the destination. */
export async function writeAtomicSnapshot(
  target: string, body: string, options: SnapshotPersistenceOptions = {},
): Promise<boolean> {
  const current = options.isCurrent ?? (() => true)
  if (!current()) return false
  const destination = path.resolve(target)
  const directory = path.dirname(destination)
  await fs.mkdir(directory, { recursive: true })
  if (!current()) return false
  const temporary = path.join(directory, path.basename(destination) + "." + randomUUID() + ".tmp")
  let created = false
  try {
    const file = await fs.open(temporary, "wx", 0o600)
    created = true
    try {
      await file.writeFile(body, "utf8")
      await file.sync()
    } finally {
      await file.close()
    }
    const rename = options.rename ?? fs.rename
    for (let attempt = 0; ; attempt++) {
      if (!current()) return false
      try {
        await rename(temporary, destination)
        return true
      } catch (error) {
        const code = (error as NodeJS.ErrnoException | undefined)?.code
        if ((options.platform ?? process.platform) !== "win32"
            || !code || !windowsRetryCodes.has(code) || attempt >= windowsRetryDelays.length) throw error
        await (options.sleep ?? delay)(windowsRetryDelays[attempt]!)
      }
    }
  } finally {
    if (created) await fs.rm(temporary, { force: true }).catch(() => undefined)
  }
}
