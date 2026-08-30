export const workerRepairPrompt = (input: {
  fingerprint?: string
  failedCriterion?: string | null
  missingEvidence?: string[]
}) =>
  [
    "Repair only the rejected WorkUnit and its owned paths.",
    "Failure fingerprint: " + (input.fingerprint ?? "unknown"),
    "Failed criterion: " + (input.failedCriterion ?? "unknown"),
    "Missing evidence: " + (input.missingEvidence?.join("; ") || "none reported"),
  ].join("\n")

export const integrationRepairPrompt = (input: {
  fingerprint?: string
  failedCriterion?: string | null
  missingEvidence?: string[]
}) =>
  [
    "Repair only the rejected root integration scope.",
    `Failure fingerprint: ${input.fingerprint ?? "unknown"}`,
    `Failed criterion: ${input.failedCriterion ?? "unknown"}`,
    `Missing evidence: ${input.missingEvidence?.join("; ") || "none reported"}`,
  ].join("\n")
