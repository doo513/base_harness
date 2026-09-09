import { createHash } from "node:crypto"

interface SecretValue { label: string; value: string }

export class SecretRegistry {
  private readonly values = new Map<string, SecretValue>()

  register(label: string, value: string | undefined): void {
    if (!value) return
    const variants = new Set([value, encodeURIComponent(value)])
    if (value.includes(":")) variants.add(Buffer.from(value).toString("base64"))
    for (const item of variants) {
      if (item.length < 4) continue
      const digest = createHash("sha256").update(item).digest("hex")
      this.values.set(digest, { label, value: item })
    }
  }

  redactText(text: string): string {
    let result = text
    const ordered = [...this.values.values()].sort((a, b) => b.value.length - a.value.length)
    for (const secret of ordered) result = result.split(secret.value).join(`[REDACTED:${secret.label}]`)
    return result
  }

  redact<T>(value: T): T {
    if (typeof value === "string") return this.redactText(value) as T
    if (Array.isArray(value)) return value.map((item) => this.redact(item)) as T
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, this.redact(item)])) as T
    return value
  }
}
