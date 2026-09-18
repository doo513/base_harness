import { randomUUID } from "node:crypto"
import type { ContractQuestionBatch, HostContractContext } from "@base-harness/domain-contracts"

/** Application-only port, supplied by the existing Question service. Not a model tool or HTTP API. */
export type ContractQuestionService = (batch: ContractQuestionBatch) => Promise<readonly (readonly string[])[] | undefined>

function assertCurrent(current: () => boolean) {
  if (!current()) throw Object.assign(new Error("CONTRACT_ANSWER_STALE"), { code: "CONTRACT_ANSWER_STALE" })
}

// The only answer writer. Callers cannot submit a trust bit, issue ID or session binding.
function recordServiceResponse(context: HostContractContext, batch: ContractQuestionBatch, response: Awaited<ReturnType<ContractQuestionService>>) {
  if (!response || response.length !== batch.issues.length) { batch.status = "cancelled"; return false }
  let answered = 0
  for (let index = 0; index < batch.issues.length; index++) {
    const answer = response[index]
    if (!Array.isArray(answer) || !answer.length || answer.some((value) => typeof value !== "string" || !value.trim())) continue
    context.answers.push({ batchId: batch.id, issueId: batch.issues[index]!.id, answer: [...answer] })
    answered++
  }
  batch.status = answered === batch.issues.length ? "answered" : answered ? "partial" : "cancelled"
  return batch.status === "answered"
}

/** No answer is an approval. Completed clarification always requires a new checked candidate. */
export async function collectContractAnswers(
  context: HostContractContext,
  ask: ContractQuestionService,
  current: () => boolean,
  updated: () => void,
) {
  assertCurrent(current)
  if (context.outcome !== "needs_input") return
  if (context.questions.some((batch) => batch.status === "pending")) throw Object.assign(new Error("CONTRACT_QUESTION_ACTIVE"), { code: "CONTRACT_QUESTION_ACTIVE" })
  while (context.outcome === "needs_input") {
    const answered = new Set(context.answers.map((answer) => answer.issueId))
    const issues = context.issues.filter((issue) => !answered.has(issue.id)).slice(0, 3)
    if (!issues.length) {
      context.outcome = "revision_required"
      updated()
      return
    }
    const batch: ContractQuestionBatch = {
      id: randomUUID(), sessionID: context.sessionID, runId: context.runId,
      candidateRevision: context.candidateRevision, contentHash: context.contentHash,
      issues: structuredClone(issues), status: "pending",
    }
    context.questions.push(batch)
    updated()
    let response: Awaited<ReturnType<ContractQuestionService>>
    try { response = await ask(structuredClone(batch)) }
    catch (error) {
      batch.status = "cancelled"
      assertCurrent(current)
      updated()
      throw error
    }
    if (!current()) batch.status = "cancelled"
    assertCurrent(current)
    const complete = recordServiceResponse(context, batch, response)
    updated()
    if (!complete) return
  }
}
