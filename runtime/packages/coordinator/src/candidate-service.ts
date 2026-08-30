import * as Orchestration from "@base-harness/core/orchestration"

export class CandidateService {
  readonly store = new Orchestration.WorkspaceCandidateStore()

  activate() {
    Orchestration.bindWorkspaceCandidateStore(this.store)
  }

  get api() {
    this.activate()
    return Orchestration
  }

  reset() {
    this.activate()
    Orchestration.resetForTest()
  }
}
