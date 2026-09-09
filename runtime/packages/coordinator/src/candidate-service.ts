import * as Orchestration from "@base-harness/workspace/orchestration"

export class CandidateService {
  readonly store = new Orchestration.WorkspaceCandidateStore()
  private readonly scoped = new Proxy(Orchestration, {
    get: (target, property, receiver) => {
      const value = Reflect.get(target, property, receiver)
      if (typeof value !== "function" || property === "OrchestrationError" || property === "WorkspaceCandidateStore") return value
      return (...args: unknown[]) => Orchestration.withWorkspaceCandidateStore(this.store, () => Reflect.apply(value, target, args))
    },
  })

  activate() {
    // Retained for callers that acquired the service before instance-scoped APIs.
    // No process-global store is switched.
  }

  get api() {
    return this.scoped
  }

  reset() {
    this.store.clear()
  }
}
