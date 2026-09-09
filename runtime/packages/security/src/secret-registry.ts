import { createHash, randomBytes } from "node:crypto"

const REDACTED = "[REDACTED]"
const SENSITIVE_KEY =
  /(?:authorization|api[-_]?key|auth|bearer|cookie|credential|cred|password|refresh|secret|token|비밀|인증)/i
const VALUE_PATTERNS = [
  /\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b/gi,
  /\bsk-(?:ant-)?[A-Za-z0-9_-]{16,}\b/g,
  /\bAIza[0-9A-Za-z_-]{20,}\b/g,
  /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g,
  /\bgh[pousr]_[A-Za-z0-9_]{20,}\b/g,
  /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
] as const

export interface SecretFinding {
  path: string
  source: string
  digest: string
}

interface Entry {
  value: string
  source: string
  digest: string
}

const scalar = (value: unknown): string[] => {
  if (typeof value === "string") return [value]
  if (Array.isArray(value)) return value.flatMap(scalar)
  if (value && typeof value === "object") return Object.values(value).flatMap(scalar)
  return []
}

export class SecretRegistry {
  private readonly entries = new Map<string, Entry>()
  private readonly salt = randomBytes(16).toString("hex")

  register(value: unknown, source = "credential") {
    for (const item of scalar(value)) {
      if (!item) continue
      const digest = createHash("sha256").update(this.salt).update(item).digest("hex")
      this.entries.set(item, { value: item, source, digest })
    }
  }

  registerEnvironment(environment: NodeJS.ProcessEnv = process.env) {
    for (const [name, value] of Object.entries(environment)) {
      if (!value || !SENSITIVE_KEY.test(name)) continue
      this.register(value, `environment:${name}`)
    }
  }

  snapshot() {
    const next = new SecretRegistry()
    for (const entry of this.entries.values()) next.register(entry.value, entry.source)
    next.registerEnvironment()
    return next
  }

  redactText(value: string, exactScalar = false) {
    let output = value
    const entries = [...this.entries.values()].sort((a, b) => b.value.length - a.value.length)
    for (const entry of entries) {
      if (entry.value.length < 8) {
        if (!exactScalar || output !== entry.value) continue
        output = REDACTED
        continue
      }
      output = output.split(entry.value).join(REDACTED)
      output = output.split(encodeURIComponent(entry.value)).join(REDACTED)
      output = output.split(Buffer.from(entry.value).toString("base64")).join(REDACTED)
    }
    for (const pattern of VALUE_PATTERNS) output = output.replace(pattern, REDACTED)
    return output
  }

  redact(value: unknown, key = ""): unknown {
    if (typeof value === "string") return SENSITIVE_KEY.test(key) ? REDACTED : this.redactText(value, true)
    if (Array.isArray(value)) return value.map((item) => this.redact(item))
    if (value && typeof value === "object") {
      return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, this.redact(item, name)]))
    }
    return value
  }

  findings(value: unknown, path = "$"): SecretFinding[] {
    const found: SecretFinding[] = []
    const visit = (item: unknown, current: string) => {
      if (typeof item === "string") {
        for (const entry of this.entries.values()) {
          if (item.includes(entry.value)) found.push({ path: current, source: entry.source, digest: entry.digest })
        }
        return
      }
      if (Array.isArray(item)) return item.forEach((child, index) => visit(child, `${current}[${index}]`))
      if (item && typeof item === "object") {
        for (const [name, child] of Object.entries(item)) visit(child, `${current}.${name}`)
      }
    }
    visit(value, path)
    return found
  }

  clear() {
    this.entries.clear()
  }
}

export class SecretRegistryHub {
  readonly processRegistry = new SecretRegistry()
  private readonly runs = new Map<string, SecretRegistry>()

  constructor(environment: NodeJS.ProcessEnv = process.env) {
    this.processRegistry.registerEnvironment(environment)
  }

  register(value: unknown, source = "credential") {
    this.processRegistry.register(value, source)
    for (const registry of this.runs.values()) registry.register(value, source)
  }

  openRun(runId: string) {
    const existing = this.runs.get(runId)
    if (existing) return existing
    const registry = this.processRegistry.snapshot()
    this.runs.set(runId, registry)
    return registry
  }

  forRun(runId: string) {
    return this.runs.get(runId) ?? this.openRun(runId)
  }

  redact(runId: string, value: unknown) {
    return this.forRun(runId).redact(value)
  }

  findings(runId: string, value: unknown) {
    return this.forRun(runId).findings(value)
  }

  closeRun(runId: string) {
    this.runs.get(runId)?.clear()
    this.runs.delete(runId)
  }

  clear() {
    for (const registry of this.runs.values()) registry.clear()
    this.runs.clear()
    this.processRegistry.clear()
  }
}

export const GlobalSecretRegistryHub = new SecretRegistryHub()
export const GlobalSecretRegistry = GlobalSecretRegistryHub.processRegistry

export const SecretRedaction = { REDACTED, SENSITIVE_KEY }

