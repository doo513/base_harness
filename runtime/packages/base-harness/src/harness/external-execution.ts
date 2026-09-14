import { Coordinator, type GoalContractProposal, type HarnessStatus } from "./coordinator-service"
import { normalizeBackendSelection, ExecutionBackends } from "./execution/backend-router"
import { BackendExecutionError } from "./execution/backend"

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" ? value as Record<string, unknown> : undefined
}

function normalizeWorkPaths(value: unknown, field: "readSet" | "writeSet", required: boolean): string[] {
  if (!Array.isArray(value) || (required && value.length === 0)) {
    throw new Error(`EXTERNAL_PLANNING_PROTOCOL_INVALID: ${field} must be a non-empty path array`)
  }
  return value.map((item) => {
    if (typeof item !== "string" || !item.trim() || item.includes("\0")) {
      throw new Error(`EXTERNAL_PLANNING_PROTOCOL_INVALID: ${field} contains an invalid path`)
    }
    const normalized = item.trim().replaceAll("\\", "/").replace(/^\.\/+/, "")
    if (!normalized) throw new Error(`EXTERNAL_PLANNING_PROTOCOL_INVALID: ${field} contains an invalid path`)
    return normalized
  })
}

function normalizePredicate(value: unknown) {
  const predicate = record(value)
  const type = typeof predicate?.type === "string" ? predicate.type : undefined
  if (type === "pytest") return { type: "command_exit", expectedExitCode: 0 }
  if (!predicate || !type || !new Set([
    "exists", "content_contains", "content_equals", "sha256", "command_exit", "output_contains",
  ]).has(type)) {
    throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: predicate type is not supported")
  }
  if (["content_contains", "content_equals", "sha256", "output_contains"].includes(type)
      && typeof predicate.value !== "string") {
    throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: predicate.value must be a string")
  }
  if (type === "content_contains" && !predicate.value) {
    throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: content_contains requires a non-empty value")
  }
  if (type === "command_exit" && typeof predicate.expectedExitCode !== "number") {
    throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: command_exit requires expectedExitCode")
  }
  if (type === "output_contains" && predicate.stream !== undefined
      && predicate.stream !== "stdout" && predicate.stream !== "stderr") {
    throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: output_contains stream must be stdout or stderr")
  }
  return predicate
}

function extractJSON(text: string): Record<string, unknown> {
  for (let start = text.indexOf("{"); start >= 0; start = text.indexOf("{", start + 1)) {
    let depth = 0
    let quoted = false
    let escaped = false
    for (let index = start; index < text.length; index++) {
      const character = text[index]
      if (quoted) {
        if (escaped) escaped = false
        else if (character === "\\") escaped = true
        else if (character === '"') quoted = false
        continue
      }
      if (character === '"') {
        quoted = true
        continue
      }
      if (character === "{") depth += 1
      if (character === "}") {
        depth -= 1
        if (depth === 0) {
          try {
            const value = record(JSON.parse(text.slice(start, index + 1)))
            if (value && (value.contract !== undefined || value.goalContract !== undefined) && value.workGraph !== undefined) {
              return value
            }
          } catch {
            // Ignore prose and malformed balanced objects, then try the next object.
          }
          break
        }
      }
    }
  }
  throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: expected one JSON planning object")
}

function planningProposal(value: Record<string, unknown>) {
  const contract = record(value.contract ?? value.goalContract)
  const graph = record(value.workGraph)
  if (
    !contract || !Array.isArray(contract.criteria) || !Array.isArray(contract.claims) ||
    !record(contract.interpretation)
  ) {
    throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: contract is missing criteria, claims, or interpretation")
  }
  if (!graph || !Array.isArray(graph.units) || !Array.isArray(graph.integrationPaths)) {
    throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: WorkGraph is missing units or integrationPaths")
  }
  if (graph.integrationPaths.length > 0 || graph.units.some((unit) => {
    const item = record(unit)
    return Boolean(item && Array.isArray(item.integrationRequests) && item.integrationRequests.length > 0)
  })) {
    throw new Error("EXTERNAL_INTEGRATION_UNSUPPORTED: external candidates cannot enter root integration")
  }
  const units = graph.units.map((unit) => {
    const item = record(unit)
    if (!item) throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: WorkUnit is not an object")
    if (typeof item.id !== "string" || !item.id.trim()
        || typeof item.title !== "string" || !item.title.trim()
        || typeof item.instructions !== "string" || !item.instructions.trim()
        || !Array.isArray(item.claimIds) || item.claimIds.length === 0
        || !Array.isArray(item.criterionIds)
        || !Array.isArray(item.readSet)
        || !Array.isArray(item.writeSet) || item.writeSet.length === 0
        || !Array.isArray(item.integrationRequests)) {
      throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: every WorkUnit needs instructions, Claim binding, and at least one writeSet path")
    }
    return {
      ...item,
      readSet: normalizeWorkPaths(item.readSet, "readSet", false),
      writeSet: normalizeWorkPaths(item.writeSet, "writeSet", true),
      agentType: "general",
    }
  })
  const claims = contract.claims.map((claim) => {
    const item = record(claim)
    if (!item) throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: Claim is not an object")
    const scope = record(item.scope)
    if (!scope || !Array.isArray(scope.targets) || scope.targets.length === 0
        || scope.targets.some((target) => typeof target !== "string" || !target.trim())) {
      throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: claim.scope.targets must contain a path")
    }
    if (!Array.isArray(scope.capabilities) || scope.capabilities.length === 0
        || scope.capabilities.some((capability) => typeof capability !== "string" || !capability.trim())) {
      throw new Error("EXTERNAL_PLANNING_PROTOCOL_INVALID: claim.scope.capabilities must contain a capability")
    }
    return {
      ...item,
      kind: item.kind === "behavioral" ? "behavior" : item.kind,
      predicate: normalizePredicate(item.predicate),
    }
  })
  return { contract: { ...contract, claims }, graph: { ...graph, units } }
}

async function requestPlanning(input: {
  sessionID: string
  workspace: string
  goal: string
  selection: Parameters<typeof ExecutionBackends.execute>[0]["selection"]
}) {
  let lastError: unknown
  for (let attempt = 0; attempt < 2; attempt++) {
    const planning = await ExecutionBackends.execute({
      sessionID: input.sessionID,
      scopeID: input.sessionID,
      phase: "plan",
      workspace: input.workspace,
      prompt: JSON.stringify({
        protocol: "base-harness-external-planning-v1",
        attempt,
        goal: input.goal,
        response: {
          contract: {
            goal: input.goal,
            criteria: [{ criterionId: "criterion-id", statement: "required observable result", claimIds: ["claim-id"], required: true, risk: "low" }],
            claims: [{
              claimId: "claim-id",
              criterionIds: ["criterion-id"],
              origin: "user",
              statement: "verifiable claim",
              kind: "artifact",
              scope: { targets: ["literal workspace path"], capabilities: ["capability"], exclusions: [] },
              applicability: {
                os: "current",
                arch: "current",
                runtime: "current",
                provider: input.selection.backendId,
                model: input.selection.modelId,
                tools: {},
                dependencyLockHash: "current",
                configHash: "current",
                workspaceRevision: "current",
              },
              predicate: { type: "exists" },
              verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["auto"], minIndependentFamilies: 1 },
            }],
            constraints: [],
            interpretation: { version: 1, candidates: [] },
          },
          workGraph: {
            units: [{ id: "unit-id", title: "implementation unit", instructions: "implementation instructions", claimIds: ["claim-id"], criterionIds: ["criterion-id"], dependsOn: [], readSet: ["literal path"], writeSet: ["literal path"], integrationRequests: [] }],
            integrationPaths: [],
          },
        },
        constraints: [
          "Do not call tools during planning; use only the supplied goal and return the complete proposed object.",
          "Return exactly one JSON object and no markdown.",
          "Use only these predicate types: exists, content_contains, content_equals, sha256, command_exit, output_contains. For a pytest or test-suite claim, use command_exit with expectedExitCode 0; do not invent a pytest predicate.",
          "Predicate fields: content_contains/content_equals/sha256/output_contains require value:string; command_exit requires expectedExitCode:number; output_contains may set stream to stdout or stderr.",
          "Claim kind must be one of: artifact, execution, behavior, configuration, negative, external. Use behavior, not behavioral.",
          "Every claim.scope must have at least one target path and at least one non-empty capability string. Artifact implementation claims may use capabilities [\"create\", \"modify\"], and behavioral test claims may use [\"execute\", \"verify\"].",
          "Every WorkUnit must have at least one writeSet path because the Coordinator does not dispatch a read-only implementation unit. Put test or verification Claims on the implementation WorkUnit instead of creating a separate unit with writeSet: [].",
          "Do not edit files, run shell commands, call tools that write, or claim Evidence or Ready.",
          "Every required criterion must be covered by at least one WorkUnit.",
          ...(attempt === 0 ? [] : [
            "The previous response was not valid for this protocol. Return the complete object again.",
            ...(lastError instanceof Error ? ["Repair the previous protocol error: " + lastError.message] : []),
          ]),
        ],
      }),
      selection: input.selection,
      mutationPolicy: "forbid",
      routeWrite: async () => {
        throw new BackendExecutionError("BACKEND_SCOPE_VIOLATION", "External planning is read-only")
      },
    })
    try {
      return planningProposal(extractJSON(planning.output))
    } catch (error) {
      lastError = error
    }
  }
  throw new BackendExecutionError(
    "BACKEND_PROTOCOL_ERROR",
    lastError instanceof Error ? lastError.message : "EXTERNAL_PLANNING_PROTOCOL_INVALID",
    lastError,
  )
}

export async function executeExternalGoal(input: {
  sessionID: string
  workspace: string
  goal: string
  context: unknown
  execution: unknown
  planOnly?: boolean
}): Promise<{ status: HarnessStatus; output: string }> {
  const selection = normalizeBackendSelection(input.execution)
  if (!selection || !ExecutionBackends.get(selection.backendId)) {
    throw new Error("EXECUTION_BACKEND_UNAVAILABLE")
  }
  const parsed = await requestPlanning({
    sessionID: input.sessionID,
    workspace: input.workspace,
    goal: input.goal,
    selection,
  })
  const accepted = await Coordinator.proposeContract(input.sessionID, parsed.contract as unknown as GoalContractProposal, input.context)
  if (accepted.contractStatus !== "accepted") {
    throw new Error(accepted.message ?? "EXTERNAL_CONTRACT_REJECTED")
  }
  await Coordinator.acceptWorkGraph(input.sessionID, {
    ...parsed.graph,
  }, input.context)
  if (input.planOnly) {
    return {
      status: Coordinator.status(input.sessionID),
      output: "External execution plan prepared. Use /execute to apply it.",
    }
  }
  const status = await Coordinator.verify({ sessionID: input.sessionID, reason: "completion" })
  const output = status.workers.flatMap((worker) => worker.output ? [worker.output] : []).join("\n").trim()
  return { status, output }
}
