export type HarnessControl =
  | { type: "domain.set"; domain: "develop" | "general" }
  | { type: "skill.set"; skill: "hackathon"; enabled: boolean }
  | { type: "planning.plan_once" }
  | { type: "planning.discard" }
  | { type: "planning.execute"; planId?: string }

export type PendingHarnessSelection = {
  domain: "develop" | "general"
  hackathon: boolean
  planOnce: boolean
  count: number
}

let pending: HarnessControl[] = []
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

export function queueHarnessControl(control: HarnessControl) {
  if (control.type === "domain.set") {
    pending = pending.filter((item) => item.type !== "domain.set" && item.type !== "skill.set")
    pending.push(control)
  } else if (control.type === "skill.set") {
    pending = pending.filter((item) => item.type !== "skill.set")
    if (control.enabled) pending.push(control)
  } else if (control.type === "planning.plan_once") {
    pending = pending.filter((item) => item.type !== "planning.plan_once")
    pending.push(control)
  } else if (control.type === "planning.discard") {
    pending = pending.filter((item) => item.type !== "planning.plan_once")
  }
  emit()
}

export function pendingHarnessSelection(): PendingHarnessSelection {
  let domain: PendingHarnessSelection["domain"] = "develop"
  let hackathon = false
  let planOnce = false
  for (const control of pending) {
    if (control.type === "domain.set") {
      domain = control.domain
      hackathon = false
    } else if (control.type === "skill.set") {
      hackathon = control.enabled
      if (control.enabled) domain = "develop"
    } else if (control.type === "planning.plan_once") {
      planOnce = true
    }
  }
  return { domain, hackathon, planOnce, count: pending.length }
}

export function subscribePendingHarnessControls(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export async function flushPendingHarnessControls(
  send: (control: HarnessControl) => Promise<unknown>,
) {
  const batch = pending
  pending = []
  emit()
  for (let index = 0; index < batch.length; index += 1) {
    try {
      await send(batch[index]!)
    } catch (error) {
      pending = [...batch.slice(index), ...pending]
      emit()
      throw error
    }
  }
}
