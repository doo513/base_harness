import { Effect, Schema } from "effect"
import * as Tool from "./tool"
import { registerHarnessContractProposal } from "./harness-contract-state"
import { Question } from "../question"

const StringList = Schema.mutable(Schema.Array(Schema.String))

const Criterion = Schema.Struct({
  criterionId: Schema.String,
  statement: Schema.String,
  claimIds: StringList,
  required: Schema.Boolean,
  risk: Schema.Literals(["low", "medium", "high", "critical"]),
})

const Applicability = Schema.Struct({
  os: Schema.optional(Schema.String),
  arch: Schema.optional(Schema.String),
  runtime: Schema.optional(Schema.String),
  provider: Schema.optional(Schema.String),
  model: Schema.optional(Schema.String),
  tools: Schema.optional(Schema.Record(Schema.String, Schema.String)),
  dependencyLockHash: Schema.optional(Schema.String),
  configHash: Schema.optional(Schema.String),
  workspaceRevision: Schema.optional(Schema.String),
})

const Claim = Schema.Struct({
  claimId: Schema.String,
  criterionIds: StringList,
  origin: Schema.Literals(["user", "harness_policy", "derived_dependency"]),
  statement: Schema.String,
  kind: Schema.Literals(["artifact", "execution", "behavior", "configuration", "negative", "external"]),
  scope: Schema.Struct({
    targets: StringList,
    capabilities: StringList,
    exclusions: StringList,
  }),
  applicability: Schema.optional(Applicability),
  predicate: Schema.Record(Schema.String, Schema.Unknown),
  verifierPolicy: Schema.Struct({
    minimumStrength: Schema.Literals(["structural", "execution", "behavioral", "external_oracle"]),
    allowedVerifierIds: StringList,
    minIndependentFamilies: Schema.Int.check(Schema.isGreaterThanOrEqualTo(1)),
  }),
})

export const Parameters = Schema.Struct({
  goal: Schema.String,
  criteria: Schema.mutable(Schema.Array(Criterion)),
  claims: Schema.mutable(Schema.Array(Claim)),
  constraints: Schema.optional(StringList),
})

type Proposal = Schema.Schema.Type<typeof Parameters>
type Metadata = { contractProposal: Proposal }

export const HarnessContractTool = Tool.define<typeof Parameters, Metadata, Question.Service>(
  "harness_contract",
  Effect.gen(function* () {
    const question = yield* Question.Service
    return {
      description:
        "Submit a typed GoalContract before changing workspace state. Each criterion must map bidirectionally to one or more atomic claims with scope, applicability, a typed predicate, and an allowed verifier policy.",
      parameters: Parameters,
      execute: (params: Proposal, ctx: Tool.Context<Metadata>) =>
        Effect.gen(function* () {
          const status = yield* Effect.promise(() =>
            registerHarnessContractProposal(ctx.sessionID, params, ctx),
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
            title: "GoalContract proposal",
            output: JSON.stringify({ proposal: params, kernel: status, answers }, null, 2),
            metadata: { contractProposal: params, kernelStatus: status, answers },
          }
        }).pipe(Effect.orDie),
    } satisfies Tool.DefWithoutID<typeof Parameters, Metadata>
  }),
)
