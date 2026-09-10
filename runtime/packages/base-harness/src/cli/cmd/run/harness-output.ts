import type { HarnessControl } from "@base-harness/kernel"

export type HeadlessControl = Extract<
  HarnessControl,
  { type: "domain.set" | "skill.set" | "planning.plan_once" | "planning.execute" }
>

type HeadlessDomain = Extract<HeadlessControl, { type: "domain.set" }>["domain"]

export interface HeadlessControlOptions {
  domain?: HeadlessDomain
  hackathon?: boolean
  plan?: boolean
  executePlan?: string
}

export interface ExecutePlanOptions extends HeadlessControlOptions {
  model?: string
  variant?: string
  agent?: string
  fork?: boolean
  command?: string
  message?: string
}

export interface HarnessOutputStatus {
  sessionID: string
  phase: string
  readyEligible: boolean
  planningState?: string
  planOnly?: boolean
  outcome?: string
  activePlanId?: string
  activePlanRevision?: number
  failureKind?: string | null
  assuranceLevel?: string
  effectiveProfile?: string
  [key: string]: unknown
}

const TERMINAL_PHASES = new Set(["ready", "blocked", "interrupted", "failure"])
const FAILURE_PHASES = new Set(["blocked", "interrupted", "failure"])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function invalidHarnessStatus(): never {
  throw new Error("HARNESS_STATUS_INVALID")
}

function hostErrorCode(value: unknown): string | undefined {
  if (!isRecord(value)) return undefined
  return typeof value.code === "string" ? value.code : undefined
}

export function headlessControls(options: HeadlessControlOptions): HeadlessControl[] {
  const controls: HeadlessControl[] = []
  if (options.domain) controls.push({ type: "domain.set", domain: options.domain })
  if (options.hackathon === true) {
    controls.push({ type: "skill.set", skill: "hackathon", enabled: true })
  }
  if (options.plan === true) controls.push({ type: "planning.plan_once" })
  return controls
}

export function assertExecutePlanOptions(options: ExecutePlanOptions): void {
  if (options.executePlan === undefined) return

  const conflicts = [
    options.domain !== undefined,
    options.hackathon === true,
    options.plan === true,
    Boolean(options.model),
    Boolean(options.variant),
    Boolean(options.agent),
    options.fork === true,
    Boolean(options.command),
    Boolean(options.message?.trim()),
  ]

  if (conflicts.some(Boolean)) {
    throw new Error("Cannot replace reviewed plan settings while executing a reviewed plan")
  }
}

export function unwrapHarnessStatus(value: unknown): HarnessOutputStatus {
  if (isRecord(value) && value.error !== undefined && value.error !== null) {
    const code = hostErrorCode(value.error)
    throw new Error(`Host rejected harness status${code ? ` (${code})` : ""}`)
  }

  const status = isRecord(value) && "data" in value ? value.data : value
  if (!isRecord(status)) return invalidHarnessStatus()
  if (typeof status.sessionID !== "string" || status.sessionID.length === 0) return invalidHarnessStatus()
  if (typeof status.phase !== "string" || status.phase.length === 0) return invalidHarnessStatus()
  if (typeof status.readyEligible !== "boolean") return invalidHarnessStatus()

  return status as HarnessOutputStatus
}

export function harnessEventStatus(event: unknown, rootSessionID: string): HarnessOutputStatus | undefined {
  if (!isRecord(event) || event.type !== "harness.status") return undefined
  if (!isRecord(event.properties)) return invalidHarnessStatus()

  const status = unwrapHarnessStatus(event.properties.status)
  return status.sessionID === rootSessionID ? status : undefined
}

export function harnessSettled(status: HarnessOutputStatus, planOnly: boolean): boolean {
  if (planOnly && (status.planningState === "plan_ready" || status.phase === "plan_ready")) return true
  return TERMINAL_PHASES.has(status.phase)
}

export function harnessExitCode(status: HarnessOutputStatus, planOnly: boolean): 0 | 1 {
  // Current terminal failure state always wins over stale planning metadata.
  if (FAILURE_PHASES.has(status.phase)) return 1

  if (planOnly) {
    return status.planningState === "plan_ready" || status.phase === "plan_ready" ? 0 : 1
  }

  return status.phase === "ready" && status.outcome === "ready" && status.readyEligible === true ? 0 : 1
}
