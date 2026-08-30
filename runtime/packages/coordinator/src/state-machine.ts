import type { VerificationStatus } from "@base-harness/verification"

export const nonRepairableFailure = (kind: string | null | undefined) =>
  kind === "model_provider_error" ||
  kind === "model_protocol_error" ||
  kind === "workspace_conflict" ||
  kind === "verifier_error" ||
  kind === "harness_error" ||
  kind === "unknown_failure"

export const inactiveVerification = (
  runId: string,
  scopeId: string,
  maxSameFailureRepairs = 2,
): VerificationStatus => ({
  state: "inactive",
  goal: "",
  runId,
  scopeId,
  rootScopeId: scopeId,
  criterionResults: [],
  claimResults: [],
  evidenceFamilies: [],
  evidenceRefs: [],
  candidateRefs: [],
  readyRef: null,
  maxSameFailureRepairs,
})
