import type { AutonomousDecisionResult, AutonomousResourceUsage, DecisionBasis, Json, SubjectRef } from "@base-harness/domain-contracts"
import { assertAutonomousSchema, canonicalJson } from "@base-harness/kernel"
import { Coordinator } from "./coordinator-service"
import type { BackendSelection } from "./execution/backend"
import { BackendExecutionError } from "./execution/backend"
import { ExecutionBackends } from "./execution/backend-router"

interface DecisionEnvelope {
  schemaVersion: "autonomous-backend-response-v1"
  kind: "decision"
  response: unknown
}

interface CheckEnvelope {
  schemaVersion: "autonomous-backend-response-v1"
  kind: "register_check"
  subject: SubjectRef
  parameters: Json
}

type BackendEnvelope = DecisionEnvelope | CheckEnvelope

export interface AutonomousExternalFeedback {
  requestId: string
  result: Json
}

export interface AutonomousExternalTurnResult {
  output: string
  displayText?: string
  resourceUsage: AutonomousResourceUsage
  feedback: AutonomousExternalFeedback
  decision: AutonomousDecisionResult | { accepted: true; check: unknown }
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : undefined
}

function json(value: unknown): Json {
  return JSON.parse(JSON.stringify(value)) as Json
}

function parseEnvelope(output: string): BackendEnvelope | string {
  const trimmed = output.trim()
  if (!trimmed) throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend returned an empty response")
  if (!trimmed.startsWith("{")) {
    if (trimmed.startsWith("[")) throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend response must be one object or plain text")
    return output
  }
  let parsed: unknown
  try { parsed = JSON.parse(trimmed) } catch (error) {
    throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend returned malformed JSON", error)
  }
  const value = record(parsed)
  if (!value || value.schemaVersion !== "autonomous-backend-response-v1" ||
      (value.kind !== "decision" && value.kind !== "register_check")) {
    throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend returned an unsupported response envelope")
  }
  const allowed = value.kind === "decision"
    ? new Set(["schemaVersion", "kind", "response"])
    : new Set(["schemaVersion", "kind", "subject", "parameters"])
  if (Object.keys(value).some((key) => !allowed.has(key))) {
    throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend response contains unknown fields")
  }
  if (value.kind === "decision") {
    if (!("response" in value)) throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend decision is missing response")
    return value as unknown as DecisionEnvelope
  }
  assertAutonomousSchema("subject", value.subject)
  if (!record(value.parameters)) throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend check parameters must be an object")
  return value as unknown as CheckEnvelope
}

function resourceUsage(value: unknown): AutonomousResourceUsage {
  const usage = record(value)
  if (!usage || !Number.isSafeInteger(usage.modelTokens) || (usage.modelTokens as number) < 0 ||
      !Number.isSafeInteger(usage.costMinorUnits) || (usage.costMinorUnits as number) < 0 ||
      Object.keys(usage).some((key) => key !== "modelTokens" && key !== "costMinorUnits")) {
    throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend did not report valid resource usage")
  }
  return { modelTokens: usage.modelTokens as number, costMinorUnits: usage.costMinorUnits as number }
}

/** Executes exactly one external turn inside the existing SessionPrompt loop. */
export async function autonomousExternalTurn(input: {
  sessionID: string
  runId: string
  workspace: string
  goal: string
  requestId: string
  selection: BackendSelection
  previous?: AutonomousExternalFeedback
  history?: readonly AutonomousExternalFeedback[]
}): Promise<AutonomousExternalTurnResult> {
  const capabilities = await ExecutionBackends.discover(input.selection.backendId)
  if (capabilities.autonomousDecision?.protocol !== "autonomous-decision-v1" ||
      capabilities.autonomousDecision.resourceUsage !== "reported-v1") {
    throw new BackendExecutionError("BACKEND_OPTION_UNSUPPORTED", "Selected backend does not support autonomous-decision-v1")
  }
  if (!input.selection.capabilityRevision || capabilities.revision !== input.selection.capabilityRevision) {
    throw new BackendExecutionError("BACKEND_CAPABILITY_STALE", "Autonomous backend capability revision is missing or stale")
  }
  if (!capabilities.models.includes(input.selection.modelId)) {
    throw new BackendExecutionError("BACKEND_MODEL_UNAVAILABLE", "Selected autonomous backend model is unavailable")
  }
  const providerId = "external/" + input.selection.backendId
  const lease = await Coordinator.reserveAutonomousModel(input.sessionID, input.runId, input.requestId,
    { messageId: input.requestId, providerId, modelId: input.selection.modelId }, { modelTokens: 0, costMinorUnits: 0 })
  if (lease.reservation !== "reserved" || !lease.signal) throw new Error("AUTONOMOUS_MODEL_REQUEST_REPLAY")
  let usage: AutonomousResourceUsage | undefined
  let output: string | undefined
  let envelope: BackendEnvelope | string | undefined
  let basis: DecisionBasis | undefined
  try {
    const state = Coordinator.status(input.sessionID)
    if (state.runId !== input.runId || !state.autonomous || state.autonomous.lifecycle === "closed") throw new Error("AUTONOMOUS_RUN_MISMATCH")
    basis = Coordinator.autonomousBasis(input.sessionID, input.runId)
    const result = await ExecutionBackends.execute({
      sessionID: input.sessionID,
      runId: input.runId,
      scopeID: input.runId,
      phase: "autonomous_decision",
      workspace: input.workspace,
      selection: input.selection,
      mutationPolicy: "forbid",
      signal: lease.signal,
      routeWrite: async () => { throw new BackendExecutionError("BACKEND_SCOPE_VIOLATION", "Autonomous decisions cannot publish workspace changes") },
      prompt: canonicalJson({
        protocol: "autonomous-decision-v1",
        goal: input.goal,
        state: json(state.autonomous),
        previous: input.previous ? json(input.previous) : null,
        history: json(input.history ?? []),
        response: {
          decisionEnvelope: {
            schemaVersion: "autonomous-backend-response-v1",
            kind: "decision",
            response: { kind: "final", text: "final report text", openWork: "drain",
              assessment: { status: "partial", summary: "assessment summary",
                citedObservationIds: [], uncertainties: ["remaining uncertainty"] } },
          },
          checkEnvelope: {
            schemaVersion: "autonomous-backend-response-v1",
            kind: "register_check",
            subject: "an exact SubjectRef from state",
            parameters: "a check parameter object",
          },
          plainText: "A plain-text response is recorded as a not_assessed final report.",
          rules: [
            "For a structured response, return one complete envelope object with schemaVersion, kind, and response or check fields.",
            "Do not return only the nested DecisionAction.",
            "Do not wrap JSON in markdown.",
            "Final openWork must be drain or cancel; assessment must be an object with status, summary, citedObservationIds, and uncertainties.",
          ],
          actionKinds: {
            invoke: { kind: "invoke", toolId: "registered tool id", arguments: {} },
            measure: { kind: "measure", checkRef: "exact VersionRef", subject: "exact SubjectRef" },
            ask: { kind: "ask", reason: "information", questions: ["question"] },
            delegate: { kind: "delegate", tasks: ["TaskProposal objects"] },
            amend_tasks: { kind: "amend_tasks", expectedGraphRevision: 1, changes: ["TaskAmendment objects"] },
            apply_candidate: { kind: "apply_candidate", candidate: "exact candidate SubjectRef" },
          },
        },
      }),
    })
    lease.signal.throwIfAborted()
    usage = resourceUsage(result.resourceUsage)
    if (result.backendId !== input.selection.backendId || result.modelId !== input.selection.modelId ||
        result.capabilityRevision !== input.selection.capabilityRevision ||
        canonicalJson(result.nativeOptions) !== canonicalJson(input.selection.nativeOptions) || result.changedFiles.length !== 0) {
      throw new BackendExecutionError("BACKEND_PROTOCOL_ERROR", "Autonomous backend result does not match the pinned execution binding")
    }
    output = result.output
    envelope = parseEnvelope(output)
  } finally {
    await Coordinator.settleAutonomousModel(input.sessionID, input.runId, input.requestId,
      usage ?? { modelTokens: 0, costMinorUnits: 0, complete: false })
  }
  if (output === undefined || envelope === undefined || usage === undefined || basis === undefined) throw new Error("AUTONOMOUS_EXTERNAL_RESULT_MISSING")
  let decision: AutonomousExternalTurnResult["decision"]
  let displayText: string | undefined
  if (typeof envelope === "string") {
    decision = await Coordinator.submitAutonomousDecision(input.sessionID, input.runId, input.requestId + ":decision", {
      kind: "final", text: envelope, basedOn: basis, openWork: "drain",
      assessment: { status: "not_assessed", summary: envelope, uncertainties: [], citedObservationIds: [] },
    })
    displayText = envelope
  } else if (envelope.kind === "register_check") {
    if (canonicalJson(Coordinator.autonomousBasis(input.sessionID, input.runId)) !== canonicalJson(basis)) {
      decision = { accepted: false, code: "AUTONOMOUS_STALE_BASIS" }
    } else {
      const check = Coordinator.proposeAutonomousCheck(input.sessionID, input.runId, envelope.subject, envelope.parameters)
      decision = { accepted: true, check }
    }
  } else {
    const response = record(envelope.response)
    const decisionId = input.requestId + ":decision"
    if (response?.kind === "final") {
      const text = typeof response.text === "string" ? response.text : undefined
      let validFinal = true
      try { assertAutonomousSchema("finalResponse", { ...response, basedOn: basis }) }
      catch { validFinal = false }
      if (!validFinal && text !== undefined) {
        // A malformed structured assessment has no authority. Preserve only its
        // report text through the existing plain-text not_assessed path.
        decision = await Coordinator.submitAutonomousDecision(input.sessionID, input.runId, decisionId, text)
      } else if (response.basedOn !== undefined && canonicalJson(response.basedOn) !== canonicalJson(basis)) {
        decision = { accepted: false, code: "AUTONOMOUS_STALE_BASIS" }
      } else {
        decision = await Coordinator.submitAutonomousDecision(input.sessionID, input.runId, decisionId,
          { ...response, basedOn: basis })
      }
      if (text !== undefined) displayText = text
    } else {
      decision = await Coordinator.submitAutonomousDecision(input.sessionID, input.runId, decisionId, {
        schemaVersion: "decision-v1", decisionId, basis, observationIds: [], action: envelope.response,
      })
    }
  }
  return { output, ...(displayText === undefined ? {} : { displayText }), resourceUsage: usage, decision,
    feedback: { requestId: input.requestId, result: JSON.parse(JSON.stringify(decision)) as Json } }
}
