import type { NotFoundError as StorageNotFoundError } from "@/storage/storage"
import type { Session } from "@/session/session"
import { Cause, Effect } from "effect"
import * as ApiError from "../errors"

export function mapStorageNotFound<A, R>(self: Effect.Effect<A, StorageNotFoundError, R>) {
  return self.pipe(Effect.mapError((error) => ApiError.notFound(error.message)))
}

export function mapBusy<A, R>(self: Effect.Effect<A, Session.BusyError, R>) {
  return self.pipe(
    Effect.catchTag("SessionBusyError", (error) =>
      Effect.fail(
        new ApiError.SessionBusyError({
          sessionID: error.sessionID,
          message: `Session is busy: ${error.sessionID}`,
        }),
      ),
    ),
  )
}


const controlRejections = {
  SESSION_WORKSPACE_MISMATCH: "This saved harness session belongs to another workspace.",
  SESSION_WORKSPACE_REQUIRED: "Select a workspace before changing harness session settings.",
  SESSION_SELECTION_INVALID: "The saved harness selection is not supported.",
  RUN_ACTIVE: "A run is active. Wait for it to finish or cancel it before changing execution.",
  PLAN_RUN_BLOCKED: "The Host run is blocked. Resolve the failure and rebuild the plan before execution.",
  PLAN_ID_MISMATCH: "The requested plan ID does not match the reviewed plan. Use /harness to inspect the active plan.",
  PLAN_ID_INVALID: "The plan ID is invalid. Use the exact reviewed plan ID.",
  PLAN_ID_REQUIRED: "Select a reviewed plan before executing it.",
  PLAN_REVISION_PENDING: "Plan revision is pending or interrupted. Use /plan discard, then build a new plan.",
  PLAN_STALE: "The reviewed plan is stale. Revise or discard it before execution.",
  PLAN_SUPERSEDED: "A newer plan revision exists. Review and execute the current revision.",
  PLAN_ALREADY_CONSUMED: "This plan has already been consumed. Build a new plan instead of replaying it.",
  PLAN_WORKSPACE_MISMATCH: "Execute this plan from its original workspace.",
  PLAN_SELECTION_UNAVAILABLE: "The reviewed model selection is unavailable. Build a new plan with an available model.",
} as const

export function harnessControlRejection(error: unknown): ApiError.InvalidRequestError | undefined {
  if (!(error instanceof Error) || !("code" in error) || typeof error.code !== "string") return
  if (!Object.hasOwn(controlRejections, error.code)) return
  const kind = error.code as keyof typeof controlRejections
  // Only typed codes cross this boundary; never expose raw messages, paths, or causes.
  return new ApiError.InvalidRequestError({ kind, message: controlRejections[kind] })
}

export function mapHarnessControlFailure<A, E, R>(self: Effect.Effect<A, E, R>) {
  return self.pipe(Effect.catchCause((cause): Effect.Effect<never, E | ApiError.InvalidRequestError> => {
    const rejection = harnessControlRejection(Cause.squash(cause))
    return rejection ? Effect.fail(rejection) : Effect.failCause(cause)
  }))
}
