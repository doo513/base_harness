import { Effect } from "effect"
import { EffectBridge, type Shape } from "../effect/bridge"
import { InstanceState } from "../effect/instance-state"

const executionToken = Symbol("HostExecutionContext")
const contexts = new WeakMap<object, Readonly<{
  sessionID: string
  workspace: string
  bridge: Shape
}>>()

/** Capture only inside the actual request Effect, never during service initialization. */
export function captureExecutionContext<C extends object>(sessionID: string, context: C) {
  return Effect.gen(function* () {
    const instance = yield* InstanceState.context
    const bridge = yield* EffectBridge.make()
    const token = Object.freeze({})
    contexts.set(token, Object.freeze({ sessionID, workspace: instance.directory, bridge }))
    // Host spreads retain the symbol; JSON and persisted plans cannot carry authority.
    return { ...context, [executionToken]: token }
  })
}

export function executionBridge(context: unknown, sessionID: string, workspace: string | undefined): Shape {
  const token = context && typeof context === "object"
    ? (context as { [executionToken]?: object })[executionToken]
    : undefined
  const captured = token && typeof token === "object" ? contexts.get(token) : undefined
  if (!captured || captured.sessionID !== sessionID || captured.workspace !== workspace) {
    const error = new Error("HOST_EXECUTION_CONTEXT_UNAVAILABLE")
    Object.assign(error, { code: "HOST_EXECUTION_CONTEXT_UNAVAILABLE" })
    throw error
  }
  return captured.bridge
}
