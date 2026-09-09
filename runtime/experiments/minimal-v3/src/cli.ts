#!/usr/bin/env bun
import { existsSync } from "node:fs"
import { resolve } from "node:path"
import { stdin as input, stdout as output } from "node:process"
import { createInterface } from "node:readline/promises"
import { AgentLoop } from "./agent/loop"
import { registerSubagentTool } from "./agent/subagent"
import { loadConfig, type LoadedConfig } from "./config"
import { VerificationKernel } from "./kernel"
import { McpConnections } from "./mcp/client"
import { loadPlugins } from "./plugins/loader"
import { registerOpenAICompatible } from "./providers/openai-compatible"
import { ProviderRegistry } from "./providers/registry"
import type { ModelProvider } from "./providers/types"
import { SecretRegistry } from "./security/secrets"
import { loadSkills, type Skill } from "./skills/loader"
import { registerFileTools } from "./tools/builtin/files"
import { registerShellTools } from "./tools/builtin/shell"
import { ToolRegistry } from "./tools/registry"

interface RuntimeContext {
  workspace: string
  loaded: LoadedConfig
  providers: ProviderRegistry
  tools: ToolRegistry
  mcp: McpConnections
  secrets: SecretRegistry
  providerId: string
  modelId: string
  provider: ModelProvider
  skills: Map<string, Skill>
  selectedSkill?: Skill
  lastOutcome?: Record<string, any>
}

function option(args: string[], name: string): string | undefined { const index = args.indexOf(name); return index >= 0 ? args[index + 1] : undefined }
function workspaceFor(args: string[]): string {
  const explicit = option(args, "--workspace")
  if (explicit) return resolve(explicit)
  if (args[0] && !args[0].startsWith("-") && existsSync(args[0]) && !["run", "doctor", "models", "providers"].includes(args[0])) return resolve(args[0])
  return resolve(process.env.BASE_HARNESS_LAUNCH_CWD ?? process.cwd())
}

async function createRuntime(workspace: string): Promise<RuntimeContext> {
  const loaded = await loadConfig(workspace)
  const secrets = new SecretRegistry()
  const providers = new ProviderRegistry(secrets)
  registerOpenAICompatible(providers)
  const tools = new ToolRegistry(new Set([...loaded.config.runtime.toolsets, ...Object.keys(loaded.config.mcp).map((name) => `mcp:${name}`)]))
  registerFileTools(tools)
  registerShellTools(tools)
  await loadPlugins(loaded.config.plugins, { tools, providers })
  providers.configure(loaded.config.providers)
  const providerId = loaded.config.provider
  const modelId = loaded.config.model
  const provider = providers.create(providerId)
  const mcp = new McpConnections()
  await mcp.connect(loaded.config.mcp, tools)
  const skills = await loadSkills(workspace, loaded.config.skills.paths)
  return { workspace, loaded, providers, tools, mcp, secrets, providerId, modelId, provider, skills }
}

async function runTask(context: RuntimeContext, prompt: string): Promise<void> {
  const runTools = context.tools.clone()
  registerSubagentTool({ registry: runTools, provider: context.provider, model: context.modelId, reasoningEffort: context.loaded.config.reasoningEffort, workspace: context.workspace })
  const kernel = new VerificationKernel(context.workspace, context.providerId, context.modelId, context.loaded, runTools, context.secrets)
  const loop = new AgentLoop(context.provider, context.modelId, context.loaded.config.reasoningEffort, runTools, kernel, context.loaded.config.runtime.maxIterations, context.loaded.config.runtime.maxRepairs)
  try {
    const result = await loop.run(prompt, context.selectedSkill?.content ?? "")
    context.lastOutcome = result.outcome
    context.selectedSkill = undefined
    if (result.response) output.write(result.response + "\n")
    output.write(`[harness] ${result.outcome.outcome}${result.outcome.assuranceLevel ? ` (${result.outcome.assuranceLevel})` : ""}\n`)
    if (result.outcome.outcome !== "ready") output.write(JSON.stringify(result.outcome, null, 2) + "\n")
  } finally { await kernel.dispose() }
}

async function interactive(context: RuntimeContext): Promise<void> {
  output.write(`Base Harness Runtime 3.0\nworkspace: ${context.workspace}\nmodel: ${context.providerId}:${context.modelId}\n`)
  const terminal = createInterface({ input, output })
  try {
    while (true) {
      const line = (await terminal.question("base-harness> ")).trim()
      if (!line) continue
      if (line === "/quit" || line === "/exit") break
      if (line === "/model") { output.write(`${context.providerId}:${context.modelId}\n`); continue }
      if (line.startsWith("/model ")) {
        const selection = line.slice(7).trim()
        const split = selection.indexOf(":")
        if (split < 1) { output.write("Use /model provider:model\n"); continue }
        const providerId = selection.slice(0, split)
        const modelId = selection.slice(split + 1)
        try {
          context.provider = context.providers.create(providerId)
          context.providerId = providerId
          context.modelId = modelId
          output.write(`model: ${providerId}:${modelId}\n`)
        } catch (error) { output.write(`model selection failed: ${error instanceof Error ? error.message : String(error)}\n`) }
        continue
      }
      if (line.startsWith("/models")) {
        const id = line.split(/\s+/)[1] ?? context.providerId
        try {
          for (const model of await context.providers.create(id).listModels()) output.write(`${id}:${model.id}${model.reasoningEfforts?.length ? ` [${model.reasoningEfforts.join(", ")}]` : ""}\n`)
        } catch (error) { output.write(`model catalog failed: ${error instanceof Error ? error.message : String(error)}\n`) }
        continue
      }
      if (line === "/tools") { for (const tool of context.tools.list()) output.write(`${tool.name}\t${tool.toolset}\t${tool.effect}\t${tool.risk}\n`); continue }
      if (line === "/skills") { for (const skill of context.skills.values()) output.write(`${skill.name}\t${skill.path}\n`); continue }
      if (line.startsWith("/skill ")) {
        const name = line.slice(7).trim()
        const skill = context.skills.get(name)
        if (!skill) output.write(`Unknown skill: ${name}\n`)
        else { context.selectedSkill = skill; output.write(`Attached for next task: ${name}\n`) }
        continue
      }
      if (line === "/status") { output.write(JSON.stringify(context.lastOutcome ?? { outcome: "idle" }, null, 2) + "\n"); continue }
      await runTask(context, line)
    }
  } finally { terminal.close(); await context.mcp.close() }
}

function help(): void {
  output.write("base-harness [workspace]\nbase-harness run <prompt> [--workspace path]\nbase-harness models [--workspace path]\nbase-harness providers [--workspace path]\nbase-harness doctor [--workspace path]\n")
}

async function main(): Promise<void> {
  const args = process.argv.slice(2)
  if (args.includes("--help") || args.includes("-h")) { help(); return }
  const workspace = workspaceFor(args)
  const context = await createRuntime(workspace)
  if (args[0] === "providers") { for (const id of context.providers.profileIds()) output.write(id + "\n"); await context.mcp.close(); return }
  if (args[0] === "models") {
    for (const model of await context.provider.listModels()) output.write(`${context.providerId}:${model.id}${model.reasoningEfforts?.length ? ` [${model.reasoningEfforts.join(", ")}]` : ""}\n`)
    await context.mcp.close()
    return
  }
  if (args[0] === "doctor") {
    output.write(JSON.stringify({ runtime: "3.0.0", workspace, configFiles: context.loaded.files, provider: context.providerId, model: context.modelId, tools: context.tools.list().length, skills: context.skills.size, verifier: "protocol-v4" }, null, 2) + "\n")
    await context.mcp.close()
    return
  }
  if (args[0] === "run") {
    const promptParts: string[] = []
    for (let index = 1; index < args.length; index++) {
      if (args[index] === "--workspace") { index++; continue }
      promptParts.push(args[index])
    }
    const prompt = promptParts.join(" ").trim()
    if (!prompt) throw new Error("run requires a prompt")
    try { await runTask(context, prompt) } finally { await context.mcp.close() }
    return
  }
  await interactive(context)
}

main().catch((error) => { console.error(`Base Harness failed: ${error instanceof Error ? error.message : String(error)}`); process.exitCode = 1 })
