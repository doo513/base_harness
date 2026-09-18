import type {
  AutonomousDomainModule, AutonomousPreparationInput, AutonomousPreparationResult, DecisionAction, ReadonlyValue,
} from "@base-harness/domain-contracts"
import { pinStrategy } from "./execution"

function prepare(input: ReadonlyValue<AutonomousPreparationInput>): AutonomousPreparationResult {
  if (!input.originalRequest.trim()) return { status: "invalid", code: "REQUEST_EMPTY" }
  // No claim count, inferred test strength, risk family, or solution-plan gate.
  // The caller separately checks the Intent/grant schema, provenance and lifetime.
  return { status: "proceed", context: {
    originalRequest: input.originalRequest,
    requirements: input.intent.requirements.map((item) => ({ id: item.id, text: item.text })),
    constraints: input.intent.constraints.map((item) => ({ id: item.id, text: item.text })),
    workingGoal: input.interpretation.goalSummary,
    assumptions: input.interpretation.assumptions.map((item) => ({ id: item.id, statement: item.statement })),
    openQuestions: [...input.interpretation.openQuestions],
    proposedCheckIds: [...input.interpretation.proposedCheckIds],
    environment: { ...input.environment },
  } }
}

function normalizeDecision(input: Parameters<AutonomousDomainModule["normalizeDecision"]>[0]): unknown {
  if (input.response && typeof input.response === "object" && "kind" in input.response && input.response.kind === "final") {
    if (!input.textReport) throw new Error("AUTONOMOUS_REPORT_REQUIRED")
    const candidate = input.response as Record<string, unknown>
    return { kind: "finish", report: { ...input.textReport }, openWork: candidate.openWork, assessment: structuredClone(candidate.assessment) }
  }
  if (typeof input.response !== "string") return structuredClone(input.response)
  if (!input.textReport) throw new Error("AUTONOMOUS_REPORT_REQUIRED")
  return {
    kind: "finish", report: { ...input.textReport }, openWork: "drain",
    assessment: { status: "not_assessed", summary: input.response, citedObservationIds: [], uncertainties: [] },
  } satisfies DecisionAction
}

/** Explicit execution registration, independent of DomainRegistry metadata lookup.
 * General/Develop share the minimal default mechanics. Their selected context and
 * model, not a Kernel decision tree, determine how to investigate a problem.
 */
export const builtinAutonomousDomainModules: readonly AutonomousDomainModule[] = Object.freeze(
  ["general", "develop"].map((domainId) => Object.freeze({
    id: `${domainId}:autonomous`, revision: "1", domainId, prepare, normalizeDecision,
  })),
)

export function pinAutonomousDomainModule(module: AutonomousDomainModule): AutonomousDomainModule {
  if (!module.id?.trim() || !module.revision?.trim() || !module.domainId?.trim() ||
      typeof module.prepare !== "function" || typeof module.normalizeDecision !== "function") {
    throw new Error("AUTONOMOUS_DOMAIN_MODULE_INVALID")
  }
  // Reuse the existing receiver-state guard, including class strategies.
  const preparation = pinStrategy(module, "prepare", "DOMAIN_EXECUTION_MODULE_INVALID").prepare
  const normalization = pinStrategy(module, "normalizeDecision", "DOMAIN_EXECUTION_MODULE_INVALID").normalizeDecision
  return Object.freeze({ id: module.id, revision: module.revision, domainId: module.domainId,
    prepare: preparation, normalizeDecision: normalization })
}
