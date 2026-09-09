import { randomUUID } from "node:crypto"
import { riskRank, type LoadedConfig } from "../config"
import type { SecretRegistry } from "../security/secrets"
import type { ToolRegistry } from "../tools/registry"
import { ToolExecutionError } from "../tools/types"
import type { Risk } from "../types"
import { SidecarClient } from "../verification/client"
import { contractToolSchema, materializeContract, verifierCatalog, type ContractProposal } from "./contract"
import { EvidenceJournal } from "./evidence"
import { failureEnvelope } from "./failure"

export interface KernelResult { ok: boolean; content: string }

export class VerificationKernel {
  readonly runId = `run-${randomUUID()}`
  readonly scopeId = "root"
  private sidecar?: SidecarClient
  private source?: Record<string, string>
  private contract?: Record<string, any>
  private contractRisk: Risk = "low"
  private actionCount = 0
  private readonly journal: EvidenceJournal

  constructor(
    readonly workspace: string,
    readonly providerId: string,
    readonly modelId: string,
    readonly loaded: LoadedConfig,
    readonly tools: ToolRegistry,
    private readonly secrets: SecretRegistry,
  ) {
    this.journal = new EvidenceJournal(this.runId, secrets)
    this.tools.register({
      name: "submit_goal_contract",
      toolset: "kernel",
      effect: "control",
      risk: "low",
      description: "Submit or amend the typed GoalContract before state-changing work. Use only configured verifier IDs.",
      parameters: contractToolSchema as any,
      execute: async (input) => this.submitContract(input as unknown as ContractProposal),
    })
  }

  async begin(originalRequest: string): Promise<void> {
    this.source = { sourceId: "user-root", sourceType: "user_message", text: originalRequest }
    await this.journal.open({ workspace: this.workspace, provider: this.providerId, model: this.modelId, verificationProfile: this.loaded.config.verification.profile })
    this.sidecar = await SidecarClient.start(this.runId, this.scopeId, this.secrets)
    await this.sidecar.open(this.workspace, this.source)
  }

  systemPolicy(): string {
    return [
      "You are the actor inside Base Harness Runtime.",
      "Before any state-changing tool, call submit_goal_contract with atomic Claims bound to configured verifiers.",
      "Use claimIds supplied by the accepted contract on every state-changing tool call.",
      "Tool output and your own assessment are candidate data; only the independent verifier can issue Ready.",
      `Configured verifiers: ${JSON.stringify(verifierCatalog(this.loaded.config.verification.verifiers))}`,
    ].join("\n")
  }

  async executeTool(name: string, input: Record<string, unknown>): Promise<KernelResult> {
    const definition = this.tools.get(name)
    if (!definition) return { ok: false, content: JSON.stringify({ error: "TOOL_UNAVAILABLE", tool: name }) }
    if (name === "submit_goal_contract") return this.invoke(name, input)
    const mutating = definition.effect !== "read" && definition.effect !== "control"
    if (mutating && !this.contract) return { ok: false, content: JSON.stringify({ error: "GOAL_CONTRACT_REQUIRED" }) }
    if (this.contract && riskRank(definition.risk) > riskRank(this.contractRisk)) return { ok: false, content: JSON.stringify({ error: "RISK_TIER_INSUFFICIENT", toolRisk: definition.risk, contractRisk: this.contractRisk }) }
    let claimIds: string[] = []
    try {
      const explicit = this.tools.claimIds(name, input)
      claimIds = this.contract ? (explicit.length ? explicit : this.contract.claims.map((item: any) => item.claimId)) : []
    } catch (error) {
      return { ok: false, content: JSON.stringify({ error: failureEnvelope(error, { runId: this.runId, scopeId: this.scopeId, phase: "tool.bind" }) }) }
    }
    if (this.contract && claimIds.some((id) => !this.contract.claims.some((item: any) => item.claimId === id))) return { ok: false, content: JSON.stringify({ error: "UNKNOWN_CLAIM_BINDING" }) }
    const actionId = `action-${randomUUID()}`
    if (this.contract) await this.sidecar!.openAction({ actionId, executionId: `execution-${randomUUID()}`, claimIds, tool: name, input })
    try {
      const output = await this.tools.execute(name, input, { workspace: this.workspace })
      if (this.contract) { await this.sidecar!.closeAction({ actionId, status: "completed", output }); this.actionCount++ }
      await this.journal.record("action.completed", { actionId, name, claimIds, output })
      return { ok: true, content: stringify(output) }
    } catch (error) {
      const failure = failureEnvelope(error, { runId: this.runId, scopeId: this.scopeId, actionId, phase: "tool.execute" })
      if (this.contract) { await this.sidecar!.closeAction({ actionId, status: "error", error: error instanceof Error ? error.message : String(error), metadata: { failureEnvelope: failure } }); this.actionCount++ }
      await this.journal.record("action.failed", { actionId, name, claimIds, failure })
      return { ok: false, content: JSON.stringify({ error: failure }) }
    }
  }

  private async invoke(name: string, input: Record<string, unknown>): Promise<KernelResult> {
    try { return { ok: true, content: stringify(await this.tools.execute(name, input, { workspace: this.workspace })) } }
    catch (error) { return { ok: false, content: JSON.stringify({ error: failureEnvelope(error, { runId: this.runId, scopeId: this.scopeId, phase: "contract.submit" }) }) } }
  }

  private async submitContract(proposal: ContractProposal): Promise<unknown> {
    if (!this.source || !this.sidecar) throw new ToolExecutionError("Run is not open", "RUN_NOT_OPEN")
    const revision = this.contract ? Number(this.contract.revision) + 1 : 1
    const contract = await materializeContract({ proposal, originalRequest: this.source.text, revision, contractId: this.contract?.contractId, workspace: this.workspace, provider: this.providerId, model: this.modelId, loaded: this.loaded, tools: this.tools })
    const status = await this.sidecar.propose(contract, !!this.contract)
    this.contract = contract
    this.contractRisk = proposal.criteria.reduce<Risk>((highest, criterion) => riskRank(criterion.risk) > riskRank(highest) ? criterion.risk : highest, "low")
    await this.journal.record("contract.accepted", { contract, status })
    return { accepted: true, contractId: contract.contractId, revision, claimIds: proposal.claims.map((item) => item.id), risk: this.contractRisk }
  }

  async complete(): Promise<Record<string, any>> {
    if (!this.contract) return { outcome: "blocked", failureKind: "goal_contract_missing", missingEvidence: ["No accepted GoalContract"] }
    if (!this.actionCount) return { outcome: "blocked", failureKind: "missing_action_evidence", missingEvidence: ["No contract-bound action completed"] }
    try {
      const status = await this.sidecar!.verify("completion")
      await this.journal.record("verification.outcome", status)
      return status
    } catch (error) {
      const failure = failureEnvelope(error, { runId: this.runId, scopeId: this.scopeId, phase: "verification" })
      await this.journal.record("verification.failure", failure)
      return { outcome: "failure", failureKind: "verifier_error", failureEnvelope: failure }
    }
  }

  async recordProviderFailure(error: unknown): Promise<Record<string, unknown>> {
    const failure = failureEnvelope(error, { runId: this.runId, scopeId: this.scopeId, phase: "model.complete" })
    await this.journal.record("model.failure", failure)
    return failure
  }

  async dispose(): Promise<void> { await this.sidecar?.dispose() }
}

function stringify(value: unknown): string { return typeof value === "string" ? value : JSON.stringify(value) }
