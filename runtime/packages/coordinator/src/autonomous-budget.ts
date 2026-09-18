import type { BudgetLimits } from "@base-harness/domain-contracts"
import { canonicalJson, validateBudgetLimits } from "@base-harness/kernel"

export interface ResourceUsage {
  modelTokens: number
  costMinorUnits: number
  complete?: boolean
}
interface Reservation {
  fingerprint: string
  upperBound: ResourceUsage
  actual?: ResourceUsage
}

/** Owned by one Coordinator Run, created before its first Prepare call.
 * No awaits between checking capacity and reserving it: sibling admissions are
 * atomic in the Coordinator's JS event loop. Revisions never recreate this ledger.
 */
export class AutonomousBudget {
  private readonly reservations = new Map<string, Reservation>()
  private readonly limits: BudgetLimits
  private used: ResourceUsage = { modelTokens: 0, costMinorUnits: 0 }
  private reserved: ResourceUsage = { modelTokens: 0, costMinorUnits: 0 }
  private faulted = false
  private readonly incomplete = new Set<string>()

  constructor(
    readonly budgetId: string,
    limits: BudgetLimits,
    metering: { tokens: boolean; cost: boolean },
    private readonly clock: () => number = Date.now,
  ) {
    if (!budgetId.trim()) throw new Error("AUTONOMOUS_BUDGET_ID")
    validateBudgetLimits(limits, clock(), metering)
    this.limits = structuredClone(limits)
  }

  private validUsage(value: ResourceUsage): boolean {
    return [value.modelTokens, value.costMinorUnits].every((n) => Number.isSafeInteger(n) && n >= 0) &&
      (value.complete === undefined || typeof value.complete === "boolean")
  }

  reserve(requestId: string, payload: unknown, upperBound: ResourceUsage): "reserved" | "replay" {
    if (!requestId.trim() || !this.validUsage(upperBound)) throw new Error("AUTONOMOUS_RESERVATION_INVALID")
    const fingerprint = canonicalJson({ payload, upperBound })
    const previous = this.reservations.get(requestId)
    if (previous) {
      if (previous.fingerprint !== fingerprint) throw new Error("AUTONOMOUS_REQUEST_CONFLICT")
      return "replay"
    }
    this.assertAvailable()
    if (this.reservations.size >= this.limits.maxActions ||
        upperBound.modelTokens > (this.limits.maxModelTokens ?? Number.MAX_SAFE_INTEGER) - this.used.modelTokens - this.reserved.modelTokens ||
        upperBound.costMinorUnits > (this.limits.maxCost?.minorUnits ?? Number.MAX_SAFE_INTEGER) - this.used.costMinorUnits - this.reserved.costMinorUnits) {
      throw new Error("AUTONOMOUS_BUDGET_EXHAUSTED")
    }
    this.reservations.set(requestId, { fingerprint, upperBound: { ...upperBound } })
    this.reserved.modelTokens += upperBound.modelTokens
    this.reserved.costMinorUnits += upperBound.costMinorUnits
    return "reserved"
  }

  settle(requestId: string, actual: ResourceUsage): void {
    const entry = this.reservations.get(requestId)
    if (!entry || !this.validUsage(actual)) throw new Error("AUTONOMOUS_SETTLEMENT_INVALID")
    if (entry.actual) {
      if (canonicalJson(entry.actual) !== canonicalJson(actual)) throw new Error("AUTONOMOUS_SETTLEMENT_CONFLICT")
      return
    }
    if ((this.limits.maxModelTokens !== undefined && actual.modelTokens > entry.upperBound.modelTokens) ||
        (this.limits.maxCost !== undefined && actual.costMinorUnits > entry.upperBound.costMinorUnits)) {
      // An adapter violated its conservative reservation; stop further paid work.
      this.faulted = true
      throw new Error("AUTONOMOUS_METERING_OVERRUN")
    }
    if (!this.validUsage({ modelTokens: this.used.modelTokens + actual.modelTokens, costMinorUnits: this.used.costMinorUnits + actual.costMinorUnits })) {
      this.faulted = true
      throw new Error("AUTONOMOUS_METERING_OVERFLOW")
    }
    entry.actual = { ...actual }
    if (actual.complete === false) this.incomplete.add(requestId)
    this.reserved.modelTokens -= entry.upperBound.modelTokens
    this.reserved.costMinorUnits -= entry.upperBound.costMinorUnits
    this.used.modelTokens += actual.modelTokens
    this.used.costMinorUnits += actual.costMinorUnits
  }

  assertAvailable(): void {
    if (this.faulted) throw new Error("AUTONOMOUS_METERING_FAULT")
    const now = this.clock()
    if (!Number.isFinite(now) || now >= Date.parse(this.limits.deadlineAt)) throw new Error("AUTONOMOUS_DEADLINE_EXCEEDED")
  }

  snapshot() {
    return {
      budgetId: this.budgetId, limits: structuredClone(this.limits), actions: this.reservations.size,
      used: { ...this.used }, reserved: { ...this.reserved }, faulted: this.faulted,
      pending: [...this.reservations].filter(([, entry]) => !entry.actual).map(([id]) => id),
      incompleteSettlementIds: [...this.incomplete].sort(),
    }
  }
}
