import type { VerificationProfile, VerificationTrigger } from "./types"

export interface VerificationPolicy {
  profile: VerificationProfile
  trigger: VerificationTrigger
  maxSameFailureRepairs: number
}

const rank: Record<VerificationProfile, number> = { fast: 0, adaptive: 1, strict: 2 }

export function normalizeVerificationPolicy(value: unknown): VerificationPolicy {
  const item = typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {}
  const legacyMode = item.mode
  const profile =
    item.profile === "fast" || item.profile === "adaptive" || item.profile === "strict" ? item.profile : "adaptive"
  const trigger =
    item.trigger === "auto" || item.trigger === "manual"
      ? item.trigger
      : legacyMode === "manual" || item.auto === false
        ? "manual"
        : "auto"
  return {
    profile,
    trigger,
    maxSameFailureRepairs:
      typeof item.maxSameFailureRepairs === "number" && item.maxSameFailureRepairs >= 0
        ? Math.floor(item.maxSameFailureRepairs)
        : 2,
  }
}

export function escalateProfile(configured: VerificationProfile, required: VerificationProfile) {
  return rank[required] > rank[configured] ? required : configured
}

export function profileForRisk(risk: "low" | "medium" | "high" | "critical"): VerificationProfile {
  if (risk === "high" || risk === "critical") return "strict"
  if (risk === "medium") return "adaptive"
  return "fast"
}
