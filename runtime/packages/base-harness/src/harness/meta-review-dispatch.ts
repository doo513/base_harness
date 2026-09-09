import type { MetaReviewPhase } from "@base-harness/kernel"

export interface MetaReviewDispatch {
  sessionID: string
  runId: string
  phase: MetaReviewPhase
}

/** Invocation authority lives in Host object identity, never Actor arguments or metadata. */
export class MetaReviewDispatchRegistry<Context extends object> {
  private readonly contexts = new WeakMap<Context, Readonly<MetaReviewDispatch>>()

  get(context: Context) {
    return this.contexts.get(context)
  }

  async run<T>(context: Context, dispatch: MetaReviewDispatch, operation: () => Promise<T>): Promise<T> {
    if (this.contexts.has(context)) throw new Error("META_REVIEW_DISPATCH_ACTIVE")
    this.contexts.set(context, Object.freeze({
      sessionID: dispatch.sessionID, runId: dispatch.runId, phase: dispatch.phase,
    }))
    try {
      return await operation()
    } finally {
      this.contexts.delete(context)
    }
  }
}
