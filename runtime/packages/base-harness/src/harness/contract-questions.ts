import { Effect } from "effect"
import { EffectBridge } from "../effect/bridge"
import { Question } from "../question"
import type { SessionID } from "../session/schema"
import { Coordinator } from "./coordinator-service"
import { runUntilCancelled } from "./execution-lifetime"

/** Both contract entry points use the existing Question service and Host-owned bindings. */
export const requestContractQuestions = Effect.fn("ContractQuestions.request")(function* (input: {
  sessionID: SessionID
  tool?: Question.Tool
  abort?: AbortSignal
}) {
  const question = yield* Question.Service
  const bridge = yield* EffectBridge.make()
  return yield* Effect.promise((signal) => {
    const cancelled = AbortSignal.any([signal, ...(input.abort ? [input.abort] : [])])
    return Coordinator.requestContractQuestions(input.sessionID, (batch) => bridge.promise(runUntilCancelled(
      question.ask({
        sessionID: input.sessionID,
        tool: input.tool,
        questions: batch.issues.map((issue) => ({
          question: issue.statement,
          header: "Decision",
          options: [
            { label: "Apply suggestion", description: issue.suggestedResolution ?? "Use the proposed resolution for this issue." },
            { label: "Keep requirement", description: "Keep the requirement and provide a clarification." },
          ],
          multiple: false,
          custom: true,
        })),
      }).pipe(Effect.catchTag("QuestionRejectedError", () => Effect.succeed(undefined))),
      cancelled,
    )), cancelled)
  })
})
