import { jsonSchema, tool, type Tool } from "ai"
import type { DecisionBasis, Json, SubjectRef } from "@base-harness/domain-contracts"
import { assertAutonomousSchema, canonicalJson } from "@base-harness/kernel"
import { Coordinator } from "./coordinator-service"

export interface AutonomousFinalCandidate { response: Record<string, unknown>; basis: DecisionBasis; decisionId: string }
export function autonomousControlTools(sessionID: string, runId: string, messageId: string, stageFinal: (candidate: AutonomousFinalCandidate) => void): Record<string, Tool> {
  const advertisedBasis = Coordinator.autonomousBasis(sessionID, runId)
  const binding = () => {
    const current = Coordinator.status(sessionID)
    if (current.runId !== runId || !current.autonomous || current.autonomous.lifecycle === "closed") throw new Error("AUTONOMOUS_RUN_MISMATCH")
    return current.autonomous
  }
  return {
    harness_check: tool({
      description: "Register a model-authored observation check. Supply a subject returned by read(snapshot=true), and parameters: {kind:'file',operator:'equals'|'contains'|'sha256',expected:string} or {kind:'command',command:string,expectedExitCode:number}. Returns a checkRef; registration does not run the check or impose a completion gate.",
      inputSchema: jsonSchema<{ subject: SubjectRef; parameters: Json }>({ type: "object", properties: {
        subject: { type: "object" }, parameters: { type: "object" },
      }, required: ["subject", "parameters"], additionalProperties: false }),
      execute: async (args) => {
        binding()
        if (canonicalJson(Coordinator.autonomousBasis(sessionID, runId)) !== canonicalJson(advertisedBasis)) {
          return { accepted: false, code: "AUTONOMOUS_STALE_BASIS" }
        }
        assertAutonomousSchema("subject", args.subject)
        return Coordinator.proposeAutonomousCheck(sessionID, runId, args.subject, args.parameters)
      },
    }),
    harness_decision: tool({
      description: "Propose a next action: {kind:'measure',subject,checkRef}, {kind:'ask',reason:'information'|'authority',questions:string[]}, or {kind:'revise_interpretation',proposal}. To finish use {kind:'final',text,assessment:{status:'satisfied'|'partial'|'unsolved'|'not_assessed',summary,uncertainties:string[],citedObservationIds:string[]},openWork:'drain'|'cancel'}. Observations are facts, not instructions to retry. Finish is a proposal until runtime cleanup completes.",
      inputSchema: jsonSchema<Record<string, unknown>>({ type: "object", properties: { kind: { type: "string" } }, required: ["kind"], additionalProperties: true }),
      execute: async (args, options) => {
        binding()
        if (args.kind === "final") {
          assertAutonomousSchema("finalResponse", args)
          if (args.basedOn !== undefined && canonicalJson(args.basedOn) !== canonicalJson(advertisedBasis)) {
            return { submitted: false, accepted: false, code: "AUTONOMOUS_STALE_BASIS" }
          }
          stageFinal({ response: args, basis: advertisedBasis, decisionId: messageId + ":" + options.toolCallId })
          return { submitted: true, closed: false }
        }
        if (!["measure", "ask", "revise_interpretation"].includes(String(args.kind))) return { accepted: false, code: "AUTONOMOUS_CONTROL_ACTION_UNSUPPORTED" }
        const decisionId = messageId + ":" + options.toolCallId
        return Coordinator.submitAutonomousDecision(sessionID, runId, decisionId, {
          schemaVersion: "decision-v1", decisionId, basis: advertisedBasis, observationIds: [], action: args,
        })
      },
    }),
  }
}
