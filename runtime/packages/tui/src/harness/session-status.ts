export type HarnessSessionTarget = Readonly<{ sessionID: string; directory?: string }>

export function harnessRootSession(
  sessionID: string | undefined,
  getSession: (id: string) => { parentID?: string } | undefined,
): string | undefined {
  const visited = new Set<string>()
  while (sessionID) {
    if (visited.has(sessionID)) return undefined
    visited.add(sessionID)
    const parent = getSession(sessionID)?.parentID
    if (!parent) return sessionID
    sessionID = parent
  }
}

/** Presentation-only binding. The Host remains the owner of execution state. */
export function createHarnessStatusBinding<Status extends { sessionID: string }>(ports: {
  fetch: (target: HarnessSessionTarget) => Promise<Status>
  publish: (status: Status) => void
  reset: () => void
}) {
  let target: HarnessSessionTarget | undefined
  let generation = 0
  let disposed = false

  return {
    current: () => target,
    select(next: HarnessSessionTarget | undefined) {
      if (disposed || (target?.sessionID === next?.sessionID && target?.directory === next?.directory)) return false
      target = next ? Object.freeze({ ...next }) : undefined
      generation += 1
      ports.reset()
      return true
    },
    async refresh() {
      const selected = target
      if (disposed || !selected) return
      const request = ++generation
      const next = await ports.fetch(selected)
      if (disposed || target !== selected || generation !== request) return
      if (next.sessionID !== selected.sessionID) throw new Error("HARNESS_STATUS_SESSION_MISMATCH")
      ports.publish(next)
      return next
    },
    accept(next: Status, selected: HarnessSessionTarget | undefined = target) {
      if (disposed || !selected || target !== selected || next.sessionID !== selected.sessionID) return false
      generation += 1
      ports.publish(next)
      return true
    },
    dispose() {
      disposed = true
      generation += 1
      target = undefined
    },
  }
}
