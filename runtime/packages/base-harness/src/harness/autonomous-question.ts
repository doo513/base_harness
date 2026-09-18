import { Effect } from "effect"
import type { AutonomousHostOptions } from "@base-harness/kernel-host"
import { SessionID } from "../session/schema"
import { executionBridge } from "./execution-context"
import { runUntilCancelled } from "./execution-lifetime"

/** Re-enter the request's existing question service, with Run-owned cancellation.
 * A serialized context or a reply supplied in model JSON cannot reach this port.
 */
export const askAutonomousQuestions: NonNullable<AutonomousHostOptions["ask"]> = async (input) => {
  const bridge = executionBridge(input.context, input.sessionID, input.workspace)
  const { Question } = await import("../question")
  return bridge.promise(runUntilCancelled(Effect.gen(function* () {
    const question = yield* Question.Service
    return yield* question.ask({
      sessionID: SessionID.make(input.sessionID),
      questions: input.questions.map((text) => ({ question: text, header: "Clarify", options: [] })),
    })
  }), input.signal))
}
