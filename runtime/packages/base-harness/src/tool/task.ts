import * as Tool from "./tool"
import {
  closeExplorationBudget,
  EXPLORATION_DENIED_TOOLS,
  explorationInstruction,
  normalizeExplorationRequest,
  openExplorationBudget,
  type ExplorationRequest,
} from "./exploration-budget"
import DESCRIPTION from "./task.txt"
import { ToolJsonSchema } from "./json-schema"
import { SessionV1 } from "@base-harness/core/v1/session"
import { BackgroundJob } from "@/background/job"
import { Session } from "@/session/session"
import { SessionID, MessageID } from "../session/schema"
import { MessageV2 } from "../session/message-v2"
import { Agent } from "../agent/agent"
import { deriveSubagentSessionPermission } from "../agent/subagent-permissions"
import type { SessionPrompt } from "../session/prompt"
import { Config } from "@/config/config"
import { Effect, Exit, Schema, Scope } from "effect"
import { Coordinator, Orchestration } from "../harness/coordinator-service"
import { EffectBridge } from "@/effect/bridge"
import { RuntimeFlags } from "@/effect/runtime-flags"
import { Database } from "@base-harness/core/database/database"

export interface TaskPromptOps {
  cancel(sessionID: SessionID): Effect.Effect<void>
  resolvePromptParts(template: string): Effect.Effect<SessionPrompt.PromptInput["parts"]>
  prompt(input: SessionPrompt.PromptInput): Effect.Effect<SessionV1.WithParts>
}

const id = "task"
const BACKGROUND_DESCRIPTION = [
  "Background mode: background=true launches the subagent asynchronously and returns immediately.",
  "Foreground is the default; use it when you need the result before continuing.",
  "Use background only for independent work that can run while you continue elsewhere.",
  "You will be notified automatically when it finishes.",
].join(" ")
const BACKGROUND_STARTED = [
  "The task is working in the background. You will be notified automatically when it finishes.",
  "DO NOT sleep, poll for progress, ask the task for status, or duplicate this task's work — avoid working with the same files or topics it is using.",
  "Work on non-overlapping tasks, or briefly tell the user what you launched and end your response.",
].join("\n")
const BACKGROUND_UPDATED = [
  "Additional context sent to the running background task.",
  "The task is still working in the background. You will be notified automatically when it finishes.",
  "DO NOT sleep, poll for progress, ask the task for status, or duplicate this task's work — avoid working with the same files or topics it is using.",
  "Work on non-overlapping tasks, or briefly tell the user what you sent and end your response.",
].join("\n")

const BaseParameterFields = {
  description: Schema.String.annotate({ description: "A short (3-5 words) description of the task" }),
  prompt: Schema.String.annotate({ description: "The task for the agent to perform" }),
  subagent_type: Schema.String.annotate({ description: "The type of specialized agent to use for this task" }),
  task_id: Schema.optional(Schema.String).annotate({
    description:
      "This should only be set if you mean to resume a previous task (you can pass a prior task_id and the task will continue the same subagent session as before instead of creating a fresh one)",
  }),
  command: Schema.optional(Schema.String).annotate({ description: "The command that triggered this task" }),
  work_unit_id: Schema.optional(Schema.String).annotate({
    description: "Required for implementation subagents when an accepted harness_workgraph is active",
  }),
  exploration: Schema.optional(
    Schema.Struct({
      thoroughness: Schema.Literals(["quick", "standard", "deep"]),
      maxToolCalls: Schema.optional(Schema.Number),
      maxFiles: Schema.optional(Schema.Number),
    }),
  ).annotate({
    description: "Structured exploration budget. Only valid for the explore subagent.",
  }),
}

const BaseParameters = Schema.Struct(BaseParameterFields)

export const Parameters = Schema.Struct({
  ...BaseParameterFields,
  background: Schema.optional(Schema.Boolean).annotate({
    description:
      "Run the agent in the background. You will be notified when it completes. DO NOT sleep, poll, or proactively check on its progress",
  }),
})

function renderOutput(input: {
  sessionID: SessionID
  state: "running" | "completed" | "error"
  summary?: string
  text: string
}) {
  const tag = input.state === "error" ? "task_error" : "task_result"
  return [
    `<task id="${input.sessionID}" state="${input.state}">`,
    ...(input.summary ? [`<summary>${input.summary}</summary>`] : []),
    `<${tag}>`,
    input.text,
    `</${tag}>`,
    "</task>",
  ].join("\n")
}

export const TaskTool = Tool.define(
  id,
  Effect.gen(function* () {
    const agent = yield* Agent.Service
    const background = yield* BackgroundJob.Service
    const config = yield* Config.Service
    const sessions = yield* Session.Service
    const scope = yield* Scope.Scope
    const flags = yield* RuntimeFlags.Service
    const database = yield* Database.Service

    const run = Effect.fn("TaskTool.execute")(function* (
      params: Schema.Schema.Type<typeof Parameters>,
      ctx: Tool.Context,
    ) {
      Coordinator.assertToolAllowed(ctx.sessionID, "task", params.subagent_type)
      const cfg = yield* config.get()
      if (
        params.subagent_type !== "explore" &&
        Coordinator.isManagedWorkGraph(ctx.sessionID) &&
        ctx.extra?.coordinatorDispatch !== true
      ) {
        return yield* Effect.fail(
          new Error("Implementation WorkUnits are dispatched by the Host Coordinator after harness_workgraph acceptance"),
        )
      }
      const runInBackground = params.background === true
      if (runInBackground && !flags.experimentalBackgroundSubagents) {
        return yield* Effect.fail(
          new Error("Background subagents require BASE_HARNESS_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true"),
        )
      }

      const parent = yield* sessions.get(ctx.sessionID)
      let current = parent
      let depth = 0
      while (current.parentID) {
        depth++
        current = yield* sessions.get(current.parentID)
      }
      if (depth >= (cfg.subagent_depth ?? 1)) {
        return yield* Effect.fail(
          new Error(
            `Subagent depth limit reached (${cfg.subagent_depth ?? 1}). Increase "subagent_depth" to allow nested subagents.`,
          ),
        )
      }

      if (!ctx.extra?.bypassAgentCheck) {
        yield* ctx.ask({
          permission: id,
          patterns: [params.subagent_type],
          always: ["*"],
          metadata: {
            description: params.description,
            subagent_type: params.subagent_type,
          },
        })
      }

      const next = yield* agent.get(params.subagent_type)
      if (!next) {
        return yield* Effect.fail(new Error(`Unknown agent type: ${params.subagent_type} is not a valid agent type`))
      }
      if (params.exploration && params.subagent_type !== "explore") {
        return yield* Effect.fail(new Error("exploration parameters are only valid for the explore subagent"))
      }
      const exploration =
        params.subagent_type === "explore"
          ? normalizeExplorationRequest(
              (params.exploration ?? { thoroughness: "standard" }) as ExplorationRequest,
            )
          : undefined
      const taskPrompt = exploration ? `${params.prompt}\n\n${explorationInstruction(exploration)}` : params.prompt

      const session = params.task_id
        ? yield* sessions.get(SessionID.make(params.task_id)).pipe(Effect.catchCause(() => Effect.succeed(undefined)))
        : undefined
      const childPermission = deriveSubagentSessionPermission({
        parentSessionPermission: parent.permission ?? [],
        subagent: next,
      })
      const childToolDenies = [
        ...(exploration
          ? EXPLORATION_DENIED_TOOLS.map(
              (permission) => ({
                permission,
                pattern: "*" as const,
                action: "deny" as const,
              }),
            )
          : []),
        ...(next.permission.some((rule) => rule.permission === "todowrite")
          ? []
          : [{ permission: "todowrite" as const, pattern: "*" as const, action: "deny" as const }]),
        ...(next.permission.some((rule) => rule.permission === id)
          ? []
          : [{ permission: id, pattern: "*" as const, action: "deny" as const }]),
        ...(cfg.experimental?.primary_tools?.map((permission) => ({
          permission,
          pattern: "*" as const,
          action: "deny" as const,
        })) ?? []),
      ]
      const nextSession =
        session ??
        (yield* sessions.create({
          parentID: ctx.sessionID,
          title: params.description + ` (@${next.name} subagent)`,
          agent: next.name,
          permission: [
            ...childPermission,
            ...childToolDenies.filter(
              (deny) =>
                !childPermission.some(
                  (rule) =>
                    rule.permission === deny.permission && rule.pattern === deny.pattern && rule.action === deny.action,
                ),
            ),
          ],
        }))
      if (exploration) openExplorationBudget(nextSession.id, exploration)

      const assignment = Orchestration.startChild({
        parentSessionID: ctx.sessionID,
        sessionID: nextSession.id,
        subagentType: params.subagent_type,
        workUnitId: params.work_unit_id,
      })
      if (params.work_unit_id) {
        Coordinator.registerWorkerScope(ctx.sessionID, nextSession.id, params.work_unit_id)
      }

      const msg = yield* MessageV2.get({ sessionID: ctx.sessionID, messageID: ctx.messageID }).pipe(
        Effect.provideService(Database.Service, database),
        Effect.orDie,
      )
      if (msg.info.role !== "assistant") return yield* Effect.fail(new Error("Not an assistant message"))
      const variant = msg.info.variant

      const model = next.model ?? {
        modelID: msg.info.modelID,
        providerID: msg.info.providerID,
      }
      const metadata = {
        parentSessionId: ctx.sessionID,
        sessionId: nextSession.id,
        model,
        scopeKind: assignment.kind,
        ...("workUnitId" in assignment && assignment.workUnitId ? { workUnitId: assignment.workUnitId } : {}),
        ...(assignment.claimIds.length ? { claimIds: assignment.claimIds } : {}),
        ...(runInBackground ? { background: true } : {}),
      }

      yield* ctx.metadata({
        title: params.description,
        metadata,
      })

      const ops = ctx.extra?.promptOps as TaskPromptOps
      if (!ops) return yield* Effect.fail(new Error("TaskTool requires promptOps in ctx.extra"))

      const runTaskCore = Effect.fn("TaskTool.runTask")(function* () {
        const parts = yield* ops.resolvePromptParts(taskPrompt)
        const result = yield* ops.prompt({
          messageID: MessageID.ascending(),
          sessionID: nextSession.id,
          model: {
            modelID: model.modelID,
            providerID: model.providerID,
          },
          variant: next.model ? undefined : variant,
          agent: next.name,
          parts,
        })
        if (result.info.role === "assistant" && result.info.error) {
          const message =
            "message" in result.info.error.data && typeof result.info.error.data.message === "string"
              ? result.info.error.data.message
              : result.info.error.name
          return yield* Effect.fail(new Error(`Subagent failed (task_id: ${nextSession.id}): ${message}`))
        }
        const failed = result.parts.findLast((item) => item.type === "tool" && item.state.status === "error")
        if (failed?.type === "tool" && failed.state.status === "error") {
          return yield* Effect.fail(new Error(`Subagent failed (task_id: ${nextSession.id}): ${failed.state.error}`))
        }
        return result.parts.findLast((item) => item.type === "text")?.text ?? ""
      })
      const runTask = () =>
        runTaskCore().pipe(
          Effect.onExit((exit) =>
            Effect.gen(function* () {
              yield* Effect.promise(() => Coordinator.finishWorker(nextSession.id, Exit.isSuccess(exit)))
              if (exploration) closeExplorationBudget(nextSession.id)
            }),
          ),
        )

      const inject = Effect.fn("TaskTool.injectBackgroundResult")(function* (
        state: "completed" | "error",
        text: string,
      ) {
        const currentParent = yield* sessions.get(ctx.sessionID)
        yield* ops
          .prompt({
            sessionID: ctx.sessionID,
            agent: currentParent.agent ?? ctx.agent,
            variant,
            parts: [
              {
                type: "text",
                synthetic: true,
                text: renderOutput({
                  sessionID: nextSession.id,
                  state,
                  summary:
                    state === "completed"
                      ? `Background task completed: ${params.description}`
                      : `Background task failed: ${params.description}`,
                  text,
                }),
              },
            ],
          })
          .pipe(Effect.ignore, Effect.forkIn(scope, { startImmediately: true }))
      })

      const notify = Effect.fn("TaskTool.notifyBackgroundResult")(function* (jobID: string) {
        yield* background.wait({ id: jobID }).pipe(
          Effect.flatMap((result) => {
            if (result.info?.status === "completed") return inject("completed", result.info.output ?? "")
            if (result.info?.status === "error") return inject("error", result.info.error ?? "")
            return Effect.void
          }),
          Effect.forkIn(scope, { startImmediately: true }),
        )
      })

      if (yield* background.extend({ id: nextSession.id, run: runTask() })) {
        return {
          title: params.description,
          metadata: {
            ...metadata,
            background: true,
            jobId: nextSession.id,
          },
          output: renderOutput({
            sessionID: nextSession.id,
            state: "running",
            summary: "Background task updated",
            text: BACKGROUND_UPDATED,
          }),
        }
      }

      const info = yield* background.start({
        id: nextSession.id,
        type: id,
        title: params.description,
        metadata,
        onPromote: Effect.all([
          ctx.metadata({
            title: params.description,
            metadata: { ...metadata, background: true, jobId: nextSession.id },
          }),
          notify(nextSession.id),
        ]),
        run: runTask().pipe(Effect.onInterrupt(() => ops.cancel(nextSession.id))),
      })

      function backgroundResult() {
        return {
          title: params.description,
          metadata: {
            ...metadata,
            background: true,
            jobId: info.id,
          },
          output: renderOutput({
            sessionID: nextSession.id,
            state: "running",
            summary: "Background task started",
            text: BACKGROUND_STARTED,
          }),
        }
      }

      if (runInBackground) {
        yield* notify(info.id)
        return backgroundResult()
      }

      const runCancel = yield* EffectBridge.make()
      const cancel = ops.cancel(nextSession.id)

      function onAbort() {
        runCancel.fork(cancel)
      }

      return yield* Effect.acquireUseRelease(
        Effect.sync(() => {
          ctx.abort.addEventListener("abort", onAbort)
        }),
        () =>
          Effect.gen(function* () {
            const result = yield* Effect.raceFirst(
              background.wait({ id: nextSession.id }).pipe(Effect.map((waited) => waited.info)),
              background.waitForPromotion(nextSession.id),
            )
            if (result?.metadata?.background === true) return backgroundResult()
            if (result?.status === "error") return yield* Effect.fail(new Error(result.error ?? "Task failed"))
            if (result?.status === "cancelled") return yield* Effect.fail(new Error("Task cancelled"))
            return {
              title: params.description,
              metadata,
              output: renderOutput({ sessionID: nextSession.id, state: "completed", text: result?.output ?? "" }),
            }
          }),
        (_, exit) =>
          Effect.gen(function* () {
            if (Exit.hasInterrupts(exit))
              yield* Effect.all([cancel, background.cancel(nextSession.id)], { discard: true })
          }).pipe(
            Effect.ensuring(
              Effect.sync(() => {
                ctx.abort.removeEventListener("abort", onAbort)
              }),
            ),
          ),
      )
    })

    const coordinatorBridge = yield* EffectBridge.make()
    Coordinator.registerMetaReviewer((request) => {
      const source = request.context as Tool.Context
      const reviewerContext: Tool.Context = {
        ...source,
        extra: {
          ...source.extra,
          bypassAgentCheck: true,
          coordinatorDispatch: true,
        },
        metadata: () => Effect.void,
        ask: () => Effect.void,
      }
      const prompt = JSON.stringify({
        protocol: "base-harness-meta-review-v1",
        phase: request.phase,
        attempt: request.attempt,
        artifact: request.artifact,
        priorIssues: request.priorIssues,
        response: {
          phase: request.phase,
          outcome: "pass | revise | needs_input",
          issues: [
            {
              id: "string",
              kind: "omission | contradiction | ambiguity | scope | applicability | coverage | verifier_mismatch | unsafe_assumption",
              severity: "blocking | warning",
              targetIds: ["string"],
              sourceRefs: [{ source: "string", pointer: "string", quote: "string" }],
              statement: "string",
              suggestedResolution: "string",
            },
          ],
          revisedArtifact: "include only for a safe typed correction",
        },
        constraints: {
          blockingOnlyForRequiredDecision: true,
          warningBecomesAssumption: true,
          noEvidenceOrReadyAuthority: true,
        },
      })
      return coordinatorBridge
        .promise(
          run(
            {
              description: "Meta review: " + request.phase,
              prompt,
              subagent_type: "meta-review",
              background: false,
            },
            reviewerContext,
          ),
        )
        .then((result) => result.output)
    })
    Coordinator.registerWorkerExecutor((request) => {
      const source = request.context as Tool.Context
      const coordinatorContext: Tool.Context = {
        ...source,
        extra: {
          ...source.extra,
          bypassAgentCheck: true,
          coordinatorDispatch: true,
        },
        metadata: () => Effect.void,
        ask: () => Effect.void,
      }
      return coordinatorBridge
        .promise(
          run(
            {
              description: request.unit.title,
              prompt: request.repairPrompt ?? request.unit.instructions,
              subagent_type: request.unit.agentType ?? "general",
              task_id: request.taskID,
              work_unit_id: request.unit.id,
              background: false,
            },
            coordinatorContext,
          ),
        )
        .then((result) => ({
          sessionID: String(result.metadata.sessionId),
          output: result.output,
        }))
    })
    Coordinator.registerIntegrationExecutor((request) => {
      const source = request.context as Tool.Context & {
        promptOps?: TaskPromptOps
        model?: SessionPrompt.PromptInput["model"]
        variant?: string
      }
      const ops = source.promptOps ?? (source.extra?.promptOps as TaskPromptOps | undefined)
      const model = source.model ?? (source.extra?.model as SessionPrompt.PromptInput["model"])
      const variant = source.variant ?? (source.extra?.variant as string | undefined)
      if (!ops) return Promise.reject(new Error("Root integration requires promptOps in the WorkGraph context"))
      if (!model) return Promise.reject(new Error("Root integration requires the inherited model in its context"))
      return coordinatorBridge
        .promise(
          Effect.gen(function* () {
            const integrationPrompt = request.repairPrompt ?? [
              "All Coordinator WorkUnits were independently verified and committed.",
              "Perform root integration only. Do not recreate the WorkGraph or rerun completed workers.",
              `Integration-owned paths: ${request.integrationPaths.join(", ") || "none"}`,
              `Integration requests: ${request.integrationRequests.join("; ") || "none"}`,
              "Resolve shared exports/configuration, run the required build or tests, and finish the root task.",
            ].join("\n")
            const parts = yield* ops.resolvePromptParts(integrationPrompt)
            const result = yield* ops.prompt({
              messageID: MessageID.ascending(),
              sessionID: request.rootSessionID as SessionID,
              model,
              variant,
              agent: source.agent,
              parts,
            })
            if (result.info.role === "assistant" && result.info.error) {
              return yield* Effect.fail(new Error("Root integration model response failed"))
            }
            const failed = result.parts.findLast((item) => item.type === "tool" && item.state.status === "error")
            if (failed?.type === "tool" && failed.state.status === "error") {
              return yield* Effect.fail(new Error(`Root integration tool failed: ${failed.state.error}`))
            }
          }),
        )
        .then(() => undefined)
    })

    return {
      description: flags.experimentalBackgroundSubagents
        ? [DESCRIPTION, BACKGROUND_DESCRIPTION].join("\n\n")
        : DESCRIPTION,
      parameters: Parameters,
      jsonSchema: flags.experimentalBackgroundSubagents ? undefined : ToolJsonSchema.fromSchema(BaseParameters),
      execute: (params: Schema.Schema.Type<typeof Parameters>, ctx: Tool.Context) =>
        run(params, ctx).pipe(Effect.orDie),
    }
  }),
)
