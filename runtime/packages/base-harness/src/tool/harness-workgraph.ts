import { Effect, Schema } from "effect"
import * as Tool from "./tool"
import { Coordinator, type WorkGraph } from "../harness/coordinator-service"

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
  Effect.succeed({
    description:
      "Submit the Claim-bound WorkGraph after read-only exploration and harness_contract. Literal module roots are canonicalized; cycles, unsequenced read/write conflicts, and worker ownership of integration paths are rejected.",
    parameters: Parameters,
    execute: (params: Input, ctx: Tool.Context) =>
      Effect.promise(async () => {
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
        const status = await Coordinator.acceptWorkGraph(ctx.sessionID, graph, ctx)
        return {
          title: "WorkGraph accepted",
          output: JSON.stringify({ phase: status.phase, workers: status.workers }, null, 2),
          metadata: { workGraph: graph, phase: status.phase },
        }
      }),
  }),
)
