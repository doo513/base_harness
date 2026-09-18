import type { ContractBody, ContractSubmission, GoalContract, HostContractContext, ValidatedContractCandidate } from "../src"

// Checked by tsc. The submission cannot carry Host state or verifier authority.
export function checkGoalContractTypes(submission: ContractSubmission, checked: ValidatedContractCandidate, wire: GoalContract, host: HostContractContext) {
  const body: ContractBody = submission
  // @ts-expect-error Model-authored data cannot assert acceptance.
  submission.accepted = true
  // @ts-expect-error Host answers have a separate origin and are not input fields.
  submission.answers = host.answers
  // @ts-expect-error Structural checking cannot mint Evidence or Ready.
  checked.ready = true
  const version: "goal-contract-v2" = wire.schemaVersion
  return { body, version }
}
