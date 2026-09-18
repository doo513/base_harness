import { unwrapHarnessResponse } from "./control-response"

export type HarnessControl =
  | { type: "domain.set"; domain: string }
  | { type: "skill.set"; skill: string; enabled: boolean }
  | {
      type: "execution.select"
      selection?: {
        adapterID: string
        modelID?: string
        options?: Record<string, string>
        capabilityRevision?: string
      }
    }
  | { type: "planning.plan_once" }
  | { type: "planning.discard" }
  | { type: "planning.execute"; planId?: string }

export type PendingHarnessSelection = {
  domain?: string
  skills: string[]
  planOnce: boolean
  execution?: Extract<HarnessControl, { type: "execution.select" }>["selection"]
  count: number
}

let pending: HarnessControl[] = []
const listeners = new Set<() => void>()

function emit() {
  for (const listener of listeners) listener()
}

export function queueHarnessControl(control: HarnessControl) {
  if (control.type === "domain.set") {
    pending = pending.filter((item) => item.type !== "domain.set")
    pending.push(control)
  } else if (control.type === "skill.set") {
    pending = pending.filter((item) => item.type !== "skill.set" || item.skill !== control.skill)
    pending.push(control)
  } else if (control.type === "execution.select") {
    pending = pending.filter((item) => item.type !== "execution.select")
    pending.push(control)
  } else if (control.type === "planning.plan_once") {
    pending = pending.filter((item) => item.type !== "planning.plan_once")
    pending.push(control)
  } else if (control.type === "planning.discard") {
    pending = pending.filter((item) => item.type !== "planning.plan_once")
  }
  emit()
}

export function pendingHarnessSelection(): PendingHarnessSelection {
  // This is unvalidated intent for the next new session, not resolved Host policy.
  let domain: string | undefined
  let skills: string[] = []
  let planOnce = false
  let execution: PendingHarnessSelection["execution"]
  for (const control of pending) {
    if (control.type === "domain.set") {
      domain = control.domain
    } else if (control.type === "skill.set") {
      skills = skills.filter((id) => id !== control.skill)
      if (control.enabled) skills.push(control.skill)
    } else if (control.type === "execution.select") {
      execution = control.selection
    } else if (control.type === "planning.plan_once") {
      planOnce = true
    }
  }
  return {
    domain,
    skills,
    planOnce,
    execution,
    count: pending.length,
  }
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
      unwrapHarnessResponse(await send(batch[index]!))
    } catch (error) {
      // A failed first request may create another session on retry. Replay all
      // idempotent settings so earlier accepted controls are not silently lost.
      pending = [...batch, ...pending]
      emit()
      throw error
    }
  }
}
