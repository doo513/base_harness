import type { VerificationKernel } from "../kernel"
import type { ModelProvider } from "../providers/types"
import type { ToolRegistry } from "../tools/registry"
import type { ChatMessage } from "../types"

export interface AgentRunResult { response: string; outcome: Record<string, any>; iterations: number }

export class AgentLoop {
  constructor(
    private readonly provider: ModelProvider,
    private readonly model: string,
    private readonly reasoningEffort: string | undefined,
    private readonly tools: ToolRegistry,
    private readonly kernel: VerificationKernel,
    private readonly maxIterations: number,
    private readonly maxRepairs: number,
  ) {}

  async run(prompt: string, skillContext = ""): Promise<AgentRunResult> {
    await this.kernel.begin(prompt)
    const messages: ChatMessage[] = [
      { role: "system", content: this.kernel.systemPolicy() + (skillContext ? `\n\nAttached skill:\n${skillContext}` : "") },
      { role: "user", content: prompt },
    ]
    let finalText = ""
    let repairs = 0
    for (let iteration = 1; iteration <= this.maxIterations; iteration++) {
      let turn
      try { turn = await this.provider.complete({ model: this.model, messages, tools: this.tools.schemas(), reasoningEffort: this.reasoningEffort }) }
      catch (error) { return { response: finalText, outcome: { outcome: "failure", failureEnvelope: await this.kernel.recordProviderFailure(error) }, iterations: iteration } }
      messages.push(turn.message)
      finalText = turn.message.content ?? finalText
      if (turn.message.toolCalls?.length) {
        for (const call of turn.message.toolCalls) {
          let toolInput: Record<string, unknown>
          try { toolInput = JSON.parse(call.arguments || "{}") }
          catch {
            messages.push({ role: "tool", toolCallId: call.id, content: JSON.stringify({ error: "INVALID_TOOL_JSON" }) })
            continue
          }
          const result = await this.kernel.executeTool(call.name, toolInput)
          messages.push({ role: "tool", toolCallId: call.id, content: result.content })
        }
        continue
      }
      const outcome = await this.kernel.complete()
      if (outcome.outcome === "ready") return { response: finalText, outcome, iterations: iteration }
      if (outcome.outcome === "repair" && repairs++ < this.maxRepairs) {
        messages.push({ role: "user", content: JSON.stringify({ type: "harness.repair", failedCriterion: outcome.failedCriterion, missingEvidence: outcome.missingEvidence, repairScope: outcome.repairScope, repairCount: outcome.repairCount }) })
        continue
      }
      return { response: finalText, outcome, iterations: iteration }
    }
    return { response: finalText, outcome: { outcome: "blocked", failureKind: "iteration_budget_exhausted" }, iterations: this.maxIterations }
  }
}

export async function runReadOnlySubagent(input: { provider: ModelProvider; model: string; reasoningEffort?: string; tools: ToolRegistry; workspace: string; prompt: string }): Promise<string> {
  const messages: ChatMessage[] = [{ role: "system", content: "Explore the workspace using read-only tools and return concise findings with file references." }, { role: "user", content: input.prompt }]
  for (let iteration = 0; iteration < 8; iteration++) {
    const turn = await input.provider.complete({ model: input.model, messages, reasoningEffort: input.reasoningEffort, tools: input.tools.schemas((tool) => tool.effect === "read" && tool.name !== "delegate_readonly") })
    messages.push(turn.message)
    if (!turn.message.toolCalls?.length) return turn.message.content ?? ""
    for (const call of turn.message.toolCalls) {
      try {
        const tool = input.tools.get(call.name)
        if (!tool || tool.effect !== "read") throw new Error("Subagent tool is not read-only")
        const result = await input.tools.execute(call.name, JSON.parse(call.arguments || "{}"), { workspace: input.workspace })
        messages.push({ role: "tool", toolCallId: call.id, content: typeof result === "string" ? result : JSON.stringify(result) })
      } catch (error) {
        messages.push({ role: "tool", toolCallId: call.id, content: JSON.stringify({ error: error instanceof Error ? error.message : String(error) }) })
      }
    }
  }
  return "Subagent read budget exhausted."
}
