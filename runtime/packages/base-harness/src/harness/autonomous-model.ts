import { Effect } from "effect"
import type { AutonomousResourceUsage, Json } from "@base-harness/domain-contracts"
import { Coordinator } from "./coordinator-service"
import { runUntilCancelled } from "./execution-lifetime"

/** Wrap one existing model turn; never creates another model/agent loop. */
export function autonomousModelTurn<A, E, R>(input: {
  sessionID: string
  runId: string
  requestId: string
  payload: Json
  usage(): AutonomousResourceUsage
}, work: Effect.Effect<A, E, R>) {
  return Effect.gen(function* () {
    const lease = yield* Effect.promise(() => Coordinator.reserveAutonomousModel(input.sessionID, input.runId, input.requestId, input.payload,
      { modelTokens: 0, costMinorUnits: 0 }))
    if (lease.reservation !== "reserved" || !lease.signal) throw new Error("AUTONOMOUS_MODEL_REQUEST_REPLAY")
    let complete = false
    return yield* runUntilCancelled(work, lease.signal).pipe(
      Effect.tap(() => Effect.sync(() => { complete = true })),
      Effect.ensuring(Effect.promise(() => Coordinator.settleAutonomousModel(input.sessionID, input.runId, input.requestId,
        { ...input.usage(), complete }))),
    )
  })
}
