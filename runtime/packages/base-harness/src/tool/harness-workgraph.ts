import { Effect, Schema } from "effect"
import * as Tool from "./tool"
import { Coordinator, type WorkGraph } from "../harness/coordinator-service"
import { Question } from "../question"
import { captureExecutionContext } from "../harness/execution-context"

const StringList = Schema.mutable(Schema.Array(Schema.String))
const WorkUnit = Schema.Struct({
  id: Schema.String,
  title: Schema.String,
  instructions: Schema.String,
  agentType: Schema.optional(Schema.String),
  claimIds: StringList,
  criterionIds: StringList,
  dependsOn: StringList,
  readSet: StringList,
  writeSet: StringList,
  integrationRequests: StringList,
})

export const Parameters = Schema.Struct({
  units: Schema.mutable(Schema.Array(WorkUnit)),
  integrationPaths: StringList,
})

type Input = Schema.Schema.Type<typeof Parameters>

export const HarnessWorkGraphTool = Tool.define(
  "harness_workgraph",
  Effect.gen(function* () {
    const question = yield* Question.Service
    return {
    description:
      "Submit the Claim-bound WorkGraph after read-only exploration and harness_contract. Literal module roots are canonicalized; cycles, unsequenced read/write conflicts, and worker ownership of integration paths are rejected.",
    parameters: Parameters,
      execute: (params: Input, ctx: Tool.Context) =>
        Effect.gen(function* () {
        const graph: WorkGraph = {
          units: params.units.map((unit) => ({
            ...unit,
            claimIds: [...unit.claimIds],
            criterionIds: [...unit.criterionIds],
            dependsOn: [...unit.dependsOn],
            readSet: [...unit.readSet],
            writeSet: [...unit.writeSet],
            integrationRequests: [...unit.integrationRequests],
          })),
          integrationPaths: [...params.integrationPaths],
        }
          const executionContext = yield* captureExecutionContext(ctx.sessionID, ctx)
          const status: any = yield* Effect.promise(() =>
            Coordinator.acceptWorkGraph(ctx.sessionID, graph, executionContext),
          )
          const blocking = Array.isArray(status.metaReview?.issues)
            ? status.metaReview.issues.filter(
                (issue: { severity?: string }) => issue.severity === "blocking",
              )
            : []
          let answers: ReadonlyArray<Question.Answer> | undefined
          if (status.planningState === "awaiting_input" && blocking.length > 0) {
            const questions = blocking.slice(0, 3).map(
              (issue: { statement: string; suggestedResolution?: string }) => ({
                question: issue.statement,
                header: "Required decision",
                options: [
                  {
                    label: "Apply suggestion",
                    description:
                      issue.suggestedResolution ??
                      "Use the reviewer resolution for this blocking issue.",
                  },
                  {
                    label: "Keep requirement",
                    description:
                      "Retain the current requirement and provide a custom clarification.",
                  },
                ],
                multiple: false,
                custom: true,
              }),
            )
            answers = yield* question.ask({
              sessionID: ctx.sessionID,
              tool: ctx.callID ? { messageID: ctx.messageID, callID: ctx.callID } : undefined,
              questions,
            })
          }
          return {
          title: "WorkGraph accepted",
          output: JSON.stringify(
            {
              phase: status.phase,
              workers: status.workers,
              planningState: status.planningState,
              activePlanId: status.activePlanId,
              activePlanRevision: status.activePlanRevision,
              metaReview: status.metaReview,
              answers,
            },
            null,
            2,
          ),
          metadata: {
            workGraph: graph,
            phase: status.phase,
            planningState: status.planningState,
            activePlanId: status.activePlanId,
            activePlanRevision: status.activePlanRevision,
          },
        }
        }).pipe(Effect.orDie),
    }
  }),
)
