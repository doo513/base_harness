import type { ContractSubmission } from "@base-harness/domain-contracts"
import { Effect, Schema } from "effect"
import * as Tool from "./tool"
import { registerHarnessContractProposal } from "./harness-contract-state"
import { Question } from "../question"
import { captureExecutionContext } from "../harness/execution-context"
import { requestContractQuestions } from "../harness/contract-questions"

const StringList = Schema.mutable(Schema.Array(Schema.String))

const Criterion = Schema.Struct({
  criterionId: Schema.String,
  statement: Schema.String,
  verificationTemplate: Schema.optional(Schema.String),
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
  predicate: Schema.StructWithRest(
    Schema.Struct({ type: Schema.String }),
    [Schema.Record(Schema.String, Schema.Unknown)],
  ),
  verifierPolicy: Schema.Struct({
    minimumStrength: Schema.Literals(["structural", "execution", "behavioral", "external_oracle"]),
    allowedVerifierIds: StringList,
    minIndependentFamilies: Schema.Int.check(Schema.isGreaterThanOrEqualTo(1)),
  }),
})

const SourceReference = Schema.Struct({
  source: Schema.String,
  pointer: Schema.optional(Schema.String),
  quote: Schema.optional(Schema.String),
})

const UncertaintyCandidate = Schema.Struct({
  id: Schema.String,
  kind: Schema.Literals(["multiple_interpretations", "missing_decision", "assumption", "conflict"]),
  impact: Schema.Literals([
    "implementation_choice",
    "user_preference",
    "required_criterion",
    "scope",
    "security",
    "external_effect",
    "verifier_applicability",
  ]),
  affectedClaimIds: StringList,
  affectedCriterionIds: StringList,
  sourceRefs: Schema.mutable(Schema.Array(SourceReference)),
  statement: Schema.String,
  suggestedResolution: Schema.optional(Schema.String),
})

export const Parameters = Schema.Struct({
  goal: Schema.String,
  criteria: Schema.mutable(Schema.Array(Criterion)),
  claims: Schema.mutable(Schema.Array(Claim)),
  constraints: Schema.optional(StringList),
  interpretation: Schema.Struct({
    version: Schema.Literal(1),
    candidates: Schema.mutable(Schema.Array(UncertaintyCandidate)),
  }),
})

type Proposal = ContractSubmission
// The transport schema and all runtime consumers use the same proposal shape.
const _proposalSchema: Schema.Codec<ContractSubmission, any> = Parameters
type Metadata = { contractProposal: Proposal }

export const HarnessContractTool = Tool.define<typeof Parameters, Metadata, Question.Service>(
  "harness_contract",
  Effect.gen(function* () {
    const question = yield* Question.Service
    return {
      description:
        "Submit a typed GoalContract and semantic uncertainty candidates before changing workspace state. The Kernel validates bindings; the Host requests input or review and awaits Runtime acceptance.",
      parameters: Parameters,
      execute: (params: Proposal, ctx: Tool.Context<Metadata>) =>
        Effect.gen(function* () {
          const executionContext = yield* captureExecutionContext(ctx.sessionID, ctx)
          let status = yield* Effect.promise(() =>
            registerHarnessContractProposal(ctx.sessionID, params, executionContext),
          )
          if (status.contractProcessing?.outcome === "needs_input") {
            status = yield* requestContractQuestions({
              sessionID: ctx.sessionID, abort: ctx.abort,
              tool: ctx.callID ? { messageID: ctx.messageID, callID: ctx.callID } : undefined,
            }).pipe(Effect.provideService(Question.Service, question))
          }
          const answers = status.contractProcessing?.answers
          return {
            title: "GoalContract proposal",
            output: JSON.stringify({ proposal: params, kernel: status, answers }, null, 2),
            metadata: { contractProposal: params, kernelStatus: status, answers },
          }
        }).pipe(Effect.orDie),
    } satisfies Tool.DefWithoutID<typeof Parameters, Metadata>
  }),
)
