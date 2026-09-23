import { createHash, randomUUID } from "node:crypto"
import { mkdir, readFile, realpath, rm, writeFile } from "node:fs/promises"
import { basename, dirname, isAbsolute, relative, resolve } from "node:path"
import { Effect } from "effect"
import { builtinAutonomousDomainModules } from "@base-harness/domain"
import { authorityAllows, canonicalJson } from "@base-harness/kernel"
import type { AutonomousHostInput, AutonomousHostOptions } from "@base-harness/kernel-host"
import type { AutonomousActionEffect, CheckSpec, DecisionAction, Json, Operation } from "@base-harness/domain-contracts"
import type { CoordinatorRuntime } from "./coordinator-service"
import { executionBridge } from "./execution-context"
import { runUntilCancelled } from "./execution-lifetime"
import { askAutonomousQuestions } from "./autonomous-question"
import { autonomousNativeToolOperation } from "./autonomous-capabilities"
import { Patch } from "../patch"
import { StrictSandbox } from "@base-harness/core/sandbox"

export interface AutonomousAppPolicy {
  timeoutMs?: number
  maxActions?: number
  allowExecution?: boolean
  allowMutation?: boolean
  allowDelegation?: boolean
  maxParallelTasks?: number
  maxTaskDepth?: number
  maxTotalTasks?: number
  maxModelTokens?: number
}

const sha256 = (value: unknown) => createHash("sha256").update(canonicalJson(value)).digest("hex")
const json = (value: unknown): Json => JSON.parse(JSON.stringify(value))
function context(input: AutonomousHostInput) {
  executionBridge(input.context, input.sessionID, input.workspace)
  const value = input.context as { agent?: string; messageID?: string; autonomousPolicy?: AutonomousAppPolicy }
  if (!value.agent || !value.messageID) throw new Error("AUTONOMOUS_APP_CONTEXT_REQUIRED")
  return value as Required<Pick<typeof value, "agent" | "messageID">> & typeof value
}
const policy = (input: AutonomousHostInput): AutonomousAppPolicy => ({
  allowExecution: input.domainId === "develop",
  allowMutation: input.domainId === "develop",
  allowDelegation: true,
  maxParallelTasks: 2,
  maxTaskDepth: 2,
  maxTotalTasks: 16,
  ...(context(input).autonomousPolicy ?? {}),
})
/** Explicit app composition, dormant for legacy Runs. No model loop or session map. */
export function autonomousExecutionOptions(runtime: CoordinatorRuntime): AutonomousHostOptions {
  const permissionSnapshot = async (input: AutonomousHostInput, prompt: boolean) => {
    const ctx = context(input)
    const [{ Permission }, { Session }, { Agent }, { SessionID }] = await Promise.all([
      import("../permission"), import("../session/session"), import("../agent/agent"), import("../session/schema"),
    ])
    const workspace = (await realpath(input.workspace)).replaceAll("\\", "/")
    const configured = structuredClone(policy(input))
    return executionBridge(input.context, input.sessionID, input.workspace).promise(Effect.gen(function* () {
      const permission = yield* Permission.Service
      const session = yield* (yield* Session.Service).get(SessionID.make(input.sessionID)).pipe(Effect.orDie)
      const agent = yield* (yield* Agent.Service).get(ctx.agent)
      const ruleset = Permission.merge(agent.permission, session.permission ?? [])
      const denied = (name: string) => Permission.evaluate(name, "*", ruleset).action === "deny"
      const operations: Operation[] = [
        ...(!denied("read") ? ["read" as const, "search" as const] : []),
        ...(configured.allowExecution && !denied("bash") ? ["execute" as const] : []),
        ...(configured.allowMutation && !denied("edit") ? ["mutate" as const, "publish" as const] : []),
        ...(configured.allowDelegation && !denied("task") ? ["delegate" as const] : []),
      ]
      if (prompt) for (const key of ["read", ...(configured.allowExecution ? ["bash"] : []),
        ...(configured.allowMutation ? ["edit"] : []), ...(configured.allowDelegation ? ["task"] : [])]) {
        yield* permission.ask({ sessionID: session.id, permission: key, patterns: ["*"], always: [],
          ruleset, metadata: { runId: input.runId, workspace, semantics: "autonomous-v1", sandboxOnly: true } }).pipe(Effect.orDie)
      }
      return { capabilities: operations.map((operation) => ({ operation,
        targets: [{ kind: "workspace_path" as const, selector: workspace }], exclusions: [] })),
        provenanceRefs: [{ sourceId: "app-permission:" + input.runId, sha256: sha256({ configured, ruleset, operations, workspace }) }],
        expiresAt: new Date(Date.now() + (configured.timeoutMs ?? 300_000)).toISOString() }
    }))
  }
  return {
    modules: builtinAutonomousDomainModules,
    cleanupTimeoutMs: 5000,
    // Provider/agent runtimes do not currently promise conservative token/cost
    // reservations across their internal retries. Hard caps fail explicitly.
    metering: { tokens: false, cost: false },
    limits: (input) => {
      const configured = policy(input)
      return { deadlineAt: new Date(Date.now() + (configured.timeoutMs ?? 300_000)).toISOString(),
        maxActions: configured.maxActions ?? 64, maxParallelTasks: configured.maxParallelTasks ?? 1,
        maxTaskDepth: configured.maxTaskDepth ?? 0, maxTotalTasks: configured.maxTotalTasks ?? 1,
        ...(configured.maxModelTokens === undefined ? {} : { maxModelTokens: configured.maxModelTokens }) }
    },
    authorize: (input) => permissionSnapshot(input, true),
    reauthorize: (input) => permissionSnapshot(input, false),
    ask: askAutonomousQuestions,
    adapter: async (input) => {
      const ctx = context(input)
      const bridge = executionBridge(input.context, input.sessionID, input.workspace)
      const workspace = (await realpath(input.workspace)).replaceAll("\\", "/")
      const [{ ToolRegistry }, { Permission }, { Session }, { Agent }, { SessionID, MessageID }, { ProviderV2 }, { ModelV2 }] = await Promise.all([
        import("../tool/registry"), import("../permission"), import("../session/session"), import("../agent/agent"),
        import("../session/schema"), import("@base-harness/core/provider"), import("@base-harness/core/model"),
      ])
      const candidateBindings = new Map<string, {
        candidateId: string
        revision: number
        patchHash: string
        candidateWorkspace: string
        files: Array<{ path: string; beforeHash: string | null; afterHash: string | null }>
        subject: import("@base-harness/domain-contracts").SubjectRef & { kind: "candidate" }
        receipt: import("@base-harness/domain-contracts").CandidateIntegrityReceipt
      }>()
      const canonicalTarget = async (value: string) => {
        let current = resolve(workspace, value)
        const suffix: string[] = []
        while (true) {
          try {
            current = resolve(await realpath(current), ...suffix)
            break
          } catch (error) {
            if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error
            const parent = dirname(current)
            if (parent === current) throw error
            suffix.unshift(basename(current))
            current = parent
          }
        }
        const rel = relative(workspace, current)
        if (rel === ".." || rel.startsWith(".." + (process.platform === "win32" ? "\\" : "/")) || isAbsolute(rel)) {
          throw new Error("AUTONOMOUS_TOOL_PATH")
        }
        return current.replaceAll("\\", "/")
      }
      const effects = async (action: DecisionAction): Promise<AutonomousActionEffect[]> => {
        if (action.kind === "measure") {
          const check = input.check(action.checkRef)
          const candidate = action.subject.kind === "candidate" ? candidateBindings.get(action.subject.id) : undefined
          return check.requiredCapabilities.map((operation) => ({ operation, targets:
            candidate && operation === "read"
              ? candidate.files.map((item) => ({ kind: "workspace_path" as const, selector: item.path }))
              : [{ kind: "workspace_path" as const, selector: operation === "execute" ? workspace : input.subject(action.subject).origin ?? workspace }] }))
        }
        if (action.kind === "apply_candidate") {
          const candidate = candidateBindings.get(action.candidate.id)
          if (!candidate || canonicalJson(candidate.subject) !== canonicalJson(action.candidate)) throw new Error("AUTONOMOUS_CANDIDATE_STALE")
          return [{ operation: "publish", targets: candidate.files.map((item) => ({ kind: "workspace_path", selector: item.path })) }]
        }
        if (action.kind !== "invoke") throw new Error("AUTONOMOUS_EFFECT_ACTION_UNSUPPORTED")
        const operation = autonomousNativeToolOperation(action.toolId)
        if (!operation) throw new Error("AUTONOMOUS_TOOL_EFFECT_UNREGISTERED_" + action.toolId.toUpperCase().replace(/[^A-Z0-9]+/g, "_"))
        const args = action.arguments as Record<string, Json>
        if (!args || typeof args !== "object" || Array.isArray(args)) throw new Error("AUTONOMOUS_TOOL_ARGUMENTS")
        let selected: unknown
        if (["read", "write", "edit"].includes(action.toolId)) selected = args.filePath
        else if (action.toolId === "bash") selected = args.workdir
        else selected = args.path
        if (action.toolId === "apply_patch") {
          if (typeof args.patchText !== "string") throw new Error("AUTONOMOUS_TOOL_ARGUMENTS")
          const hunks = Patch.parsePatch(args.patchText).hunks
          const targets = await Promise.all(hunks.flatMap((hunk) => [hunk.path,
            ...("move_path" in hunk && hunk.move_path ? [hunk.move_path] : [])])
            .map((item) => canonicalTarget(item)))
          if (!targets.length) throw new Error("AUTONOMOUS_TOOL_ARGUMENTS")
          return [{ operation, targets: [...new Set(targets)].map((selector) => ({ kind: "workspace_path", selector })) }]
        }
        if (selected !== undefined && typeof selected !== "string") throw new Error("AUTONOMOUS_TOOL_PATH")
        const target = await canonicalTarget(selected as string ?? ".")
        if (action.toolId === "bash" && args.mutation === "capture") {
          if (Object.keys(args).some((key) => !["command", "workdir", "timeout", "mutation"].includes(key))) {
            throw new Error("AUTONOMOUS_TOOL_ARGUMENTS")
          }
          return [
            { operation: "execute", targets: [{ kind: "workspace_path", selector: target }] },
            // Opaque commands can touch any path below the sandbox root. Only a
            // workspace-wide mutation grant can admit capture mode.
            { operation: "mutate", targets: [{ kind: "workspace_path", selector: workspace }] },
          ]
        }
        return [{ operation, targets: [{ kind: "workspace_path", selector: target }] }]
      }
      const execute = async (toolId: string, args: Json, requestId: string, signal: AbortSignal, scopeSessionID = input.sessionID) => {
        signal.throwIfAborted()
        const footprint = toolId === "task"
          ? [{ operation: "delegate" as const, targets: [{ kind: "workspace_path" as const, selector: workspace }] }]
          : await effects({ kind: "invoke", toolId, arguments: args })
        for (const item of footprint) if (!authorityAllows(input.snapshot().authority, item.operation, item.targets)) throw new Error("AUTONOMOUS_AUTHORITY_DENIED")
        const canonicalArgs = { ...args as Record<string, Json> }
        if (["read", "write", "edit"].includes(toolId)) canonicalArgs.filePath = footprint[0]!.targets[0]!.selector
        else if (toolId === "bash") canonicalArgs.workdir = footprint.find((item) => item.operation === "execute")!.targets[0]!.selector
        else if (toolId !== "apply_patch" && toolId !== "task") canonicalArgs.path = footprint[0]!.targets[0]!.selector
        const result = await bridge.promise(runUntilCancelled(Effect.gen(function* () {
          const registry = yield* ToolRegistry.Service
          const permission = yield* Permission.Service
          const session = yield* (yield* Session.Service).get(SessionID.make(scopeSessionID)).pipe(Effect.orDie)
          const agent = yield* (yield* Agent.Service).get(ctx.agent)
          const tools = yield* registry.tools({ providerID: ProviderV2.ID.make(input.executor.providerId ?? "external"),
            modelID: ModelV2.ID.make(input.executor.modelId ?? "external"), agent, permission: session.permission, sessionID: session.id })
          let matches = tools.filter((item) => item.id === toolId)
          if (!matches.length && ["write", "edit", "apply_patch"].includes(toolId)) {
            matches = (yield* registry.all()).filter((item) => item.id === toolId)
          }
          if (matches.length !== 1) throw new Error("AUTONOMOUS_TOOL_UNREGISTERED_OR_DUPLICATE")
          return yield* matches[0]!.execute(canonicalArgs, { sessionID: session.id, messageID: MessageID.make(ctx.messageID),
            agent: ctx.agent, abort: signal, callID: requestId, messages: [], metadata: () => Effect.void,
            ask: (request) => permission.ask({ ...request, sessionID: session.id,
              ruleset: Permission.merge(agent.permission, session.permission ?? []),
              tool: { messageID: MessageID.make(ctx.messageID), callID: requestId } }).pipe(Effect.orDie) })
        }), signal))
        if (toolId === "bash" && canonicalArgs.mutation === "capture") {
          const metadata = result.metadata as { capturedChanges?: Array<{
            path: string; beforeHash: string | null; afterHash: string | null; afterBase64?: string
          }> }
          if (!Array.isArray(metadata.capturedChanges)) throw new Error("AUTONOMOUS_COMMAND_CAPTURE_UNAVAILABLE")
          for (const item of metadata.capturedChanges) {
            if (!item || typeof item.path !== "string" || !item.path ||
                (item.beforeHash !== null && !/^[a-f0-9]{64}$/.test(item.beforeHash)) ||
                (item.afterHash !== null && !/^[a-f0-9]{64}$/.test(item.afterHash)) ||
                (item.afterHash === null) !== (item.afterBase64 === undefined)) {
              throw new Error("AUTONOMOUS_COMMAND_CAPTURE_INVALID")
            }
            const logical = await canonicalTarget(item.path)
            let current: Buffer | null
            try { current = await readFile(logical) }
            catch (error) {
              if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error
              current = null
            }
            const currentHash = current === null ? null : createHash("sha256").update(current).digest("hex")
            if (currentHash !== item.beforeHash) throw new Error("AUTONOMOUS_COMMAND_BASELINE_CHANGED")
            const routed = await runtime.orchestration.resolveWrite(scopeSessionID, workspace, logical)
            if (item.afterHash === null) await rm(routed.physicalPath, { force: true })
            else {
              const bytes = Buffer.from(item.afterBase64!, "base64")
              if (bytes.byteLength > 10 * 1024 * 1024 || createHash("sha256").update(bytes).digest("hex") !== item.afterHash) {
                throw new Error("AUTONOMOUS_COMMAND_CAPTURE_INVALID")
              }
              await mkdir(dirname(routed.physicalPath), { recursive: true })
              await writeFile(routed.physicalPath, bytes)
            }
          }
          delete metadata.capturedChanges
        }
        return result
      }
      const measurement = runtime.createAutonomousMeasurementPorts({ runId: input.runId, snapshotRoot: input.snapshotRoot,
        subject: input.subject, check: input.check, environmentHash: sha256({ workspace, platform: process.platform, executor: input.executor }),
        executeCommand: async (request, signal) => {
          const params = request.check.parameters as { argv: string[]; cwd: string }
          const startedAt = new Date().toISOString()
          const base = { argv: params.argv, cwd: params.cwd, startedAt, stdout: "", stderr: "" }
          try {
            const measured = input.subject(request.subject)
            const subjectWorkspace = request.subject.kind === "candidate" && measured.origin
              ? measured.origin : workspace
            if (params.argv.length !== 3 || params.argv[0] !== "/bin/sh" || params.argv[1] !== "-lc" || params.cwd !== subjectWorkspace) throw new Error("AUTONOMOUS_COMMAND_BINDING")
            let capture: { stdout: string; stderr: string; exitCode: number } | undefined
            if (subjectWorkspace === workspace) {
              const result = await execute("bash", { command: params.argv[2]!, workdir: workspace, timeout: request.check.timeoutMs,
                description: "Registered observation check" }, request.requestId, signal, taskScope(request.taskId))
              capture = result.metadata.measurement as typeof capture
            } else {
              const result = await StrictSandbox.run({ command: params.argv[2]!, workspace: subjectWorkspace,
                cwd: subjectWorkspace, config: { timeoutMs: request.check.timeoutMs }, signal })
              capture = { stdout: result.stdout, stderr: result.stderr, exitCode: result.exitCode }
              await runtime.recordIsolation(taskScope(request.taskId), result.provenance)
            }
            if (!capture || !Number.isSafeInteger(capture.exitCode) || typeof capture.stdout !== "string" || typeof capture.stderr !== "string") throw new Error("AUTONOMOUS_COMMAND_CAPTURE_UNAVAILABLE")
            return { ...base, ...capture, finishedAt: new Date().toISOString(), execution: "completed" }
          } catch (error) {
            const timedOut = (signal.aborted && signal.reason instanceof Error && signal.reason.name === "TimeoutError") ||
              (error && typeof error === "object" && (error as { code?: unknown }).code === "SANDBOX_TIMEOUT")
            if (!timedOut) signal.throwIfAborted()
            return { ...base, finishedAt: new Date().toISOString(), execution: "error",
              error: { code: timedOut ? "TIMEOUT" : "AUTONOMOUS_COMMAND_ERROR", message: timedOut ? "Registered command exceeded its measurement deadline" : error instanceof Error ? error.message : String(error) } }
          }
        },
      })
      const taskScope = (taskId: string) => {
        const unit = runtime.orchestration.snapshot(input.sessionID)?.units.find((item: { id: string }) => item.id === taskId)
        const sessionId = unit?.sessionID ?? (taskId === input.sessionID ? input.sessionID : undefined)
        if (!sessionId) throw new Error("AUTONOMOUS_TASK_SCOPE_UNAVAILABLE")
        return sessionId as string
      }
      return {
        ...measurement, resolveEffects: effects,
        reviseAuthority: async (authority) => {
          await runtime.orchestration.reviseAutonomousAuthority(input.sessionID, authority)
        },
        beginMutation: async (proposal, signal) => {
          signal.throwIfAborted()
          await runtime.orchestration.beginAutonomousMutation(taskScope(proposal.basis.taskId))
        },
        invoke: async (proposal, signal) => {
          if (proposal.action.kind !== "invoke") throw new Error("AUTONOMOUS_ACTION_BINDING")
          return json(await execute(proposal.action.toolId, proposal.action.arguments, proposal.decisionId, signal,
            taskScope(proposal.basis.taskId)))
        },
        sealCandidate: async (proposal, signal) => {
          if (proposal.action.kind !== "invoke") throw new Error("AUTONOMOUS_ACTION_BINDING")
          signal.throwIfAborted()
          const manifest = await runtime.orchestration.prepareCandidate(taskScope(proposal.basis.taskId))
          if (!manifest) return undefined
          const candidateWorkspace = await runtime.orchestration.materializeCandidate(manifest.candidateId)
          signal.throwIfAborted()
          const stored = await input.registerCandidateArtifact({ candidateId: manifest.candidateId,
            revision: manifest.revision, candidateWorkspace, files: manifest.files })
          const receipt = {
            receiptId: "candidate-receipt:" + randomUUID(),
            runId: input.runId,
            authorityRef: structuredClone(input.snapshot().authority.ref),
            candidate: structuredClone(stored.subject),
            baselineHash: sha256(manifest.files.map((item) => ({ path: item.path, beforeHash: item.beforeHash }))),
            patchHash: manifest.patchHash,
          }
          candidateBindings.set(stored.subject.id, { candidateId: manifest.candidateId, revision: manifest.revision,
            patchHash: manifest.patchHash, candidateWorkspace, files: structuredClone(manifest.files),
            subject: structuredClone(stored.subject), receipt: structuredClone(receipt) })
          return { candidate: structuredClone(stored.subject), taskId: proposal.basis.taskId,
            receipt, files: structuredClone(manifest.files) }
        },
        executeTask: async (task) => {
          task.signal.throwIfAborted()
          const workspaceScopes = task.requestedScopes.filter((scope) => scope.kind === "workspace_path").map((scope) => scope.selector)
          if (!workspaceScopes.length) throw new Error("AUTONOMOUS_TASK_WORKSPACE_SCOPE_REQUIRED")
          const reads = task.proposal.requestedCapabilities.some((operation) => ["read", "search", "execute", "mutate"].includes(operation))
            ? workspaceScopes : []
          const writes = task.proposal.requestedCapabilities.includes("mutate") ? workspaceScopes : []
          await runtime.orchestration.registerAutonomousTask({
            rootSessionID: input.sessionID, taskId: task.taskId, parentTaskId: task.parentTaskId,
            objective: task.proposal.objective, readSet: reads, writeSet: writes,
            dependsOn: task.proposal.dependsOn.map((item) => item.taskId),
          })
          const result = await runtime.executeAutonomousTask({
            rootSessionID: input.sessionID,
            runId: input.runId,
            taskId: task.taskId,
            objective: task.proposal.objective,
            readSet: reads,
            writeSet: writes,
            signal: task.signal,
            agentType: ctx.agent,
          })
          const sessionId = result.sessionID
          return {
            ...(sessionId ? { sessionId } : {}),
            output: json({ text: result.output ?? "", sessionId }),
          }
        },
        applyCandidate: async (proposal, receipt, signal) => {
          if (proposal.action.kind !== "apply_candidate") throw new Error("AUTONOMOUS_ACTION_BINDING")
          const candidate = candidateBindings.get(proposal.action.candidate.id)
          if (!candidate || canonicalJson(candidate.subject) !== canonicalJson(proposal.action.candidate) ||
              canonicalJson(candidate.receipt) !== canonicalJson(receipt)) throw new Error("AUTONOMOUS_CANDIDATE_STALE")
          signal.throwIfAborted()
          try {
            await runtime.orchestration.assertCandidateIntegrity(candidate.candidateId)
            await runtime.orchestration.commitAutonomousCandidate({ candidateId: candidate.candidateId,
              candidateRevision: candidate.revision, patchHash: candidate.patchHash, authorityRef: receipt.authorityRef })
            return { candidate: structuredClone(candidate.subject), state: "applied" as const, unresolvedEffects: [] }
          } catch (error) {
            const code = error && typeof error === "object" && typeof (error as { code?: unknown }).code === "string"
              ? (error as { code: string }).code : error instanceof Error ? error.message : "AUTONOMOUS_CANDIDATE_APPLY_FAILED"
            if (code === "CANDIDATE_ROLLBACK_INCOMPLETE") {
              return { candidate: structuredClone(candidate.subject), state: "recovery_required" as const,
                unresolvedEffects: ["Candidate publication recovery is required: " + candidate.candidateId] }
            }
            throw new Error(code, { cause: error })
          }
        },
        describeCheck: (parameters, stored): Omit<CheckSpec, "schemaVersion" | "ref" | "author"> => {
          const params = parameters as Record<string, Json>
          if (!params || typeof params !== "object" || Array.isArray(params)) throw new Error("AUTONOMOUS_CHECK_ARGUMENTS")
          const timeoutMs = params.timeoutMs ?? 30_000
          if (!Number.isSafeInteger(timeoutMs) || (timeoutMs as number) <= 0 || (timeoutMs as number) > 120_000) throw new Error("AUTONOMOUS_CHECK_TIMEOUT")
          const base = { executorId: "python-measurement", supportedSubjects: [stored.subject.kind], timeoutMs: timeoutMs as number }
          if (params.kind === "command") {
            if (typeof params.command !== "string" || !params.command.trim() || !Number.isSafeInteger(params.expectedExitCode) ||
                Object.keys(params).some((key) => !["kind", "command", "expectedExitCode", "timeoutMs"].includes(key))) throw new Error("AUTONOMOUS_CHECK_ARGUMENTS")
            const cwd = stored.subject.kind === "candidate" && stored.origin ? stored.origin : workspace
            return { ...base, requiredCapabilities: ["execute"], parameters: { kind: "command",
              argv: ["/bin/sh", "-lc", params.command], cwd, expectedExitCode: params.expectedExitCode! } }
          }
          if (params.kind !== "file" || !["equals", "contains", "sha256"].includes(String(params.operator)) || typeof params.expected !== "string" ||
              Object.keys(params).some((key) => !["kind", "operator", "expected", "timeoutMs"].includes(key))) throw new Error("AUTONOMOUS_CHECK_ARGUMENTS")
          const manifest = JSON.parse(stored.manifestJson)
          if (manifest.files.length !== 1) throw new Error("AUTONOMOUS_CHECK_SUBJECT")
          return { ...base, requiredCapabilities: ["read"], parameters: { kind: "file", path: manifest.files[0].path, operator: params.operator!, expected: params.expected } }
        },
      }
    },
  }
}
