import { createHash } from "node:crypto"
import { appendFile, mkdir, rename, writeFile } from "node:fs/promises"
import { homedir } from "node:os"
import { dirname, join } from "node:path"
import type { SecretRegistry } from "../security/secrets"

function stateRoot(): string {
  if (process.platform === "win32") return join(process.env.LOCALAPPDATA ?? join(homedir(), "AppData", "Local"), "base-harness")
  return join(process.env.XDG_STATE_HOME ?? join(homedir(), ".local", "state"), "base-harness")
}

export class EvidenceJournal {
  readonly runDirectory: string
  private head = "0".repeat(64)
  private count = 0

  constructor(readonly runId: string, private readonly secrets: SecretRegistry) { this.runDirectory = join(stateRoot(), "runs", runId) }

  async open(metadata: Record<string, unknown>): Promise<void> {
    await mkdir(this.runDirectory, { recursive: true })
    await this.record("run.open", metadata)
  }

  async record(type: string, payload: unknown): Promise<void> {
    const safe = this.secrets.redact(payload)
    const event = { sequence: ++this.count, at: new Date().toISOString(), type, previousHash: this.head, payload: safe }
    const hash = createHash("sha256").update(JSON.stringify(event)).digest("hex")
    this.head = hash
    await appendFile(join(this.runDirectory, "runtime-events.jsonl"), JSON.stringify({ ...event, hash }) + "\n", "utf8")
    const manifest = JSON.stringify({ runId: this.runId, eventCount: this.count, eventHead: this.head, updatedAt: event.at }, null, 2)
    const target = join(this.runDirectory, "runtime-manifest.json")
    const temporary = join(dirname(target), ".runtime-manifest.tmp")
    await writeFile(temporary, manifest, "utf8")
    await rename(temporary, target)
  }
}
