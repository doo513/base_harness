/** Compile-time design examples, not runtime admission or behavior tests. */
import type {
  CompletionRecord,
  DecisionBasis,
  DecisionProposal,
  ObservationReport,
  SubjectRef,
  VersionRef,
} from "./contracts"

const digest = "a".repeat(64)
const ref = (id: string, revision = 1): VersionRef => ({ id, revision, sha256: digest })
const candidate: SubjectRef & { kind: "candidate" } = { ...ref("candidate", 7), kind: "candidate" }
const report: SubjectRef & { kind: "report" } = { ...ref("report"), kind: "report" }
const basis: DecisionBasis = {
  runId: "run-1",
  taskId: "task-1",
  taskRevision: 2,
  intentRef: ref("intent"),
  interpretationRef: ref("interpretation", 3),
  authorityRef: ref("authority"),
}

export const failedMeasurement: ObservationReport = {
  schemaVersion: "observation-v1",
  observationId: "observation-1",
  requestId: "measurement-1",
  runId: basis.runId,
  taskId: basis.taskId,
  subject: candidate,
  checkRef: ref("regression-check"),
  environmentHash: digest,
  startedAt: "2026-09-18T00:00:00Z",
  finishedAt: "2026-09-18T00:00:01Z",
  producer: { kind: "verifier", id: "python", revision: "design-v1" },
  result: {
    execution: "completed",
    findings: [{
      kind: "comparison", name: "exit_code", operator: "equals",
      expected: 0, observed: 1, result: "fail",
    }],
  },
  artifacts: [{ ...ref("test-log"), kind: "report" }],
  limitations: ["The selected test failed; this does not identify its cause."],
}

// The same observation may lead to a new investigation or an honest partial finish.
export const investigate: DecisionProposal = {
  schemaVersion: "decision-v1", decisionId: "decision-investigate", basis,
  observationIds: [failedMeasurement.observationId],
  action: { kind: "invoke", toolId: "read", arguments: { filePath: "tests/example.test.ts" } },
}

export const finishPartial: DecisionProposal = {
  schemaVersion: "decision-v1", decisionId: "decision-finish", basis,
  observationIds: [failedMeasurement.observationId],
  action: {
    kind: "finish", report, openWork: "cancel",
    assessment: {
      status: "partial", summary: "Candidate retained; the failing test is unresolved.",
      citedObservationIds: [failedMeasurement.observationId],
      uncertainties: ["Cause of the failing test"],
    },
  },
}

export const partialCompletion: CompletionRecord = {
  schemaVersion: "completion-v1", runId: basis.runId,
  intentRef: basis.intentRef, interpretationRef: basis.interpretationRef,
  reason: "requested",
  assessment: finishPartial.action.kind === "finish" ? finishPartial.action.assessment : null,
  observationIds: [failedMeasurement.observationId],
  gates: [{ gateId: "required-test", state: "unmet", observationIds: [failedMeasurement.observationId] }],
  candidateDispositions: [{ candidate, state: "retained" }],
  unresolvedEffects: [], endedAt: "2026-09-18T00:00:02Z",
}

export const timedOutMeasurement: ObservationReport = {
  ...failedMeasurement,
  observationId: "observation-timeout",
  requestId: "measurement-timeout",
  result: { execution: "error", error: { code: "TIMEOUT", message: "The check did not finish." }, partialFindings: [] },
}

// Negative shape checks: these do not replace validation of untrusted wire data.
export const cannotOrderRepair: ObservationReport = {
  ...failedMeasurement,
  // @ts-expect-error Measurements cannot order a retry or declare Ready.
  outcome: "repair",
}

export const cannotGrantAuthority: DecisionProposal = {
  ...investigate,
  // @ts-expect-error A decision only references existing authority; it cannot issue a grant.
  authorityGrant: { unrestricted: true },
}

export const cannotApplyReport: DecisionProposal = {
  ...investigate,
  action: {
    kind: "apply_candidate",
    // @ts-expect-error A report is not a workspace Candidate.
    candidate: report,
  },
}

export const cannotCloseDuringPublication: CompletionRecord = {
  ...partialCompletion,
  candidateDispositions: [{
    candidate,
    // @ts-expect-error A final record cannot hide an unfinished publication.
    state: "applying",
  }],
}
