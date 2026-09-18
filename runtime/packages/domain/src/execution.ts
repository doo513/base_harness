import type {
  ContractBody,
  DirectExecutionProposal,
  DomainExecutionProposal,
  DomainExecutionErrorCode,
  DomainExecutionModule,
  DomainExecutionModuleResolver,
  DomainExecutionOverlayModule,
  DomainOperation,
  DomainOverlayPreparationInput,
  DomainOverlayProposalInput,
  DomainPreparation,
  DomainPreparationInput,
  DomainProposalInput,
  ReadonlyValue,
  StrategyIdentity,
  WorkGraph,
  WorkUnit,
} from "@base-harness/domain-contracts"

const identifierPattern = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const operations = new Set<DomainOperation>(["read", "search", "question", "control", "mutate", "execute", "delegate"])

export class DomainExecutionError extends Error {
  constructor(readonly code: DomainExecutionErrorCode, detail?: string) {
    super(detail ? `${code}:${detail}` : code)
    this.name = "DomainExecutionError"
  }
}

function identifier(value: unknown): value is string {
  return typeof value === "string" && identifierPattern.test(value)
}

function object(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined
}

function exactKeys(value: Record<string, unknown>, allowed: readonly string[]) {
  if (Object.keys(value).some((key) => !allowed.includes(key))) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "unknown field")
  }
}

function strings(value: unknown, field: string, required = false): string[] {
  if (value === undefined && !required) return []
  if (!Array.isArray(value) || (required && value.length === 0)) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", field)
  }
  const output = value.map((item) => {
    if (typeof item !== "string" || !item.trim() || item.includes("\0")) {
      throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", field)
    }
    return item.trim()
  })
  if (new Set(output).size !== output.length) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", `${field}:duplicate`)
  }
  return output
}

function pathList(value: unknown, field: string, required = false) {
  return strings(value, field, required).map((item) => {
    const normalized = item.replaceAll("\\", "/").replace(/^\.\/+/, "").replace(/\/{2,}/g, "/")
    const segments = normalized.split("/")
    if (!normalized || normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized)
        || segments.includes("..")) {
      throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", field)
    }
    return normalized
  })
}

function preparation(input: DomainPreparationInput, domainId: "general" | "develop"): DomainPreparation {
  if (input.selection.domain !== domainId || input.policy.domainId !== domainId
      || !input.goal.trim() || !input.workspace.trim()) {
    throw new DomainExecutionError("DOMAIN_PREPARATION_INVALID", domainId)
  }
  const allowedOperations = input.policy.allowedOperations.map((operation) => {
    if (!operations.has(operation as DomainOperation)) {
      throw new DomainExecutionError("DOMAIN_PREPARATION_INVALID", "operation")
    }
    return operation as DomainOperation
  })
  const common = {
    schemaVersion: "domain-preparation-v1" as const,
    domainId,
    goal: input.goal,
    workspace: input.workspace,
    allowedOperations,
    allowedSubagentTypes: [...input.policy.allowedSubagentTypes],
    overlays: [],
    skills: input.skills.map((skill) => ({ ...skill })),
    environment: { ...input.environment },
  }
  if (domainId === "general") return {
    ...common,
    mode: "read",
    instructions: [
      "Use read, search, lookup, and inspection operations only; do not change workspace files.",
      "Return research output as candidate data. Only the existing verifier may create Evidence or Ready.",
    ],
  }
  return {
    ...common,
    mode: "develop",
    instructions: [
      "Use the accepted GoalContract as the scope for direct work or a WorkGraph.",
      "Workspace changes must use the existing tool or Candidate transaction path and remain verifier-gated.",
    ],
  }
}

function normalizeDirect(raw: Record<string, unknown>, input: DomainProposalInput, domain: "general" | "develop"): DirectExecutionProposal {
  exactKeys(raw, ["kind", "dispatch", "instruction", "mutationPolicy"])
  const dispatch = raw.dispatch === undefined ? "attached" : raw.dispatch
  if (dispatch !== "attached" && dispatch !== "adapter") {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "dispatch")
  }
  const instruction = typeof raw.instruction === "string" ? raw.instruction.trim() : input.preparation.goal.trim()
  if (!instruction) throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "instruction")
  const requested = raw.mutationPolicy
  const mutationPolicy = requested === undefined
    ? domain === "general" || dispatch === "adapter" ? "forbid" : "capture"
    : requested
  if (mutationPolicy !== "forbid" && mutationPolicy !== "capture") {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "mutationPolicy")
  }
  if (domain === "general" && mutationPolicy !== "forbid") {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_FORBIDDEN", "general mutation")
  }
  // Direct external mutation has no Candidate transaction. Develop must use a WorkGraph for that path.
  if (dispatch === "adapter" && mutationPolicy !== "forbid") {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_FORBIDDEN", "adapter direct mutation")
  }
  return { kind: "direct", dispatch, instruction, mutationPolicy }
}

function unit(raw: unknown, claimIds: Set<string>, criterionIds: Set<string>): WorkUnit {
  const value = object(raw)
  if (!value) throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "WorkUnit")
  exactKeys(value, [
    "id", "title", "instructions", "agentType", "claimIds", "criterionIds", "dependsOn",
    "readSet", "writeSet", "integrationRequests",
  ])
  if (!identifier(value.id)) throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "WorkUnit.id")
  const title = typeof value.title === "string" && value.title.trim() ? value.title.trim() : value.id
  const instructions = typeof value.instructions === "string" && value.instructions.trim()
    ? value.instructions.trim()
    : title
  const claims = strings(value.claimIds, "claimIds", true)
  const criteria = strings(value.criterionIds, "criterionIds")
  if (claims.some((id) => !claimIds.has(id)) || criteria.some((id) => !criterionIds.has(id))) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_BINDING_INVALID", value.id)
  }
  if (value.agentType !== undefined && !identifier(value.agentType)) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "agentType")
  }
  return {
    id: value.id,
    title,
    instructions,
    ...(value.agentType ? { agentType: value.agentType as string } : {}),
    claimIds: claims,
    criterionIds: criteria,
    dependsOn: strings(value.dependsOn, "dependsOn"),
    readSet: pathList(value.readSet, "readSet"),
    writeSet: pathList(value.writeSet, "writeSet", true),
    integrationRequests: strings(value.integrationRequests, "integrationRequests"),
  }
}

function normalizeGraph(raw: Record<string, unknown>, contract: ContractBody): WorkGraph {
  exactKeys(raw, ["kind", "graph"])
  const graph = object(raw.graph)
  if (!graph) throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "WorkGraph")
  exactKeys(graph, ["units", "integrationPaths"])
  if (!Array.isArray(graph.units) || graph.units.length === 0 || graph.units.length > 64) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "WorkGraph.units")
  }
  const claims = new Set(contract.claims.map((claim) => claim.claimId))
  const criteria = new Set(contract.criteria.map((criterion) => criterion.criterionId))
  const units = graph.units.map((value) => unit(value, claims, criteria))
  const ids = new Set(units.map((value) => value.id))
  if (ids.size !== units.length || units.some((value) => value.dependsOn.some((id) => id === value.id || !ids.has(id)))) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "WorkGraph.dependencies")
  }
  const visiting = new Set<string>(), visited = new Set<string>()
  const byId = new Map(units.map((value) => [value.id, value]))
  const visit = (id: string) => {
    if (visiting.has(id)) throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "WorkGraph.cycle")
    if (visited.has(id)) return
    visiting.add(id)
    for (const dependency of byId.get(id)!.dependsOn) visit(dependency)
    visiting.delete(id)
    visited.add(id)
  }
  for (const id of ids) visit(id)
  const required = contract.claims.map((claim) => claim.claimId)
  const covered = new Set(units.flatMap((value) => value.claimIds))
  if (required.some((id) => !covered.has(id))) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_BINDING_INVALID", "required claims")
  }
  return { units, integrationPaths: pathList(graph.integrationPaths, "integrationPaths") }
}

function validateProposalContext(input: DomainProposalInput, domainId: "general" | "develop") {
  if (input.binding.runId !== input.runId || input.binding.selection.domain !== domainId
      || input.binding.policy.domainId !== domainId || input.preparation.domainId !== domainId) {
    throw new DomainExecutionError("DOMAIN_RUN_MISMATCH", domainId)
  }
  const proposal = object(input.proposal)
  if (!proposal || (proposal.kind !== "direct" && proposal.kind !== "work_graph")) {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_INVALID", "kind")
  }
  return proposal
}

export const generalExecutionModule: DomainExecutionModule = Object.freeze({
  id: "general-default",
  revision: "1",
  domainId: "general",
  preparation: Object.freeze({
    id: "general-context",
    revision: "1",
    prepare: (input: ReadonlyValue<DomainPreparationInput>) => preparation(input as DomainPreparationInput, "general"),
  }),
  proposal: Object.freeze({
    id: "general-direct-result",
    revision: "1",
    normalize(input: ReadonlyValue<DomainProposalInput>): DomainExecutionProposal {
      const raw = validateProposalContext(input as DomainProposalInput, "general")
      if (raw.kind !== "direct") throw new DomainExecutionError("DOMAIN_PROPOSAL_FORBIDDEN", "general WorkGraph")
      return normalizeDirect(raw, input as DomainProposalInput, "general")
    },
  }),
})

export const developExecutionModule: DomainExecutionModule = Object.freeze({
  id: "develop-default",
  revision: "1",
  domainId: "develop",
  preparation: Object.freeze({
    id: "develop-context",
    revision: "1",
    prepare: (input: ReadonlyValue<DomainPreparationInput>) => preparation(input as DomainPreparationInput, "develop"),
  }),
  proposal: Object.freeze({
    id: "develop-direct-or-workgraph",
    revision: "1",
    normalize(input: ReadonlyValue<DomainProposalInput>): DomainExecutionProposal {
      const value = input as DomainProposalInput
      const raw = validateProposalContext(value, "develop")
      return raw.kind === "direct" ? normalizeDirect(raw, value, "develop") : {
        kind: "work_graph" as const,
        graph: normalizeGraph(raw, value.contract as ContractBody),
      }
    },
  }),
})

function hackathonPreparation(input: DomainOverlayPreparationInput): DomainPreparation {
  const index = input.selection.skills.indexOf(input.overlayId)
  if (input.overlayId !== "hackathon" || input.selection.domain !== "develop" || index < 0
      || input.policy.skillRevisions[index] !== input.overlayRevision
      || !input.policy.requiresPlan || !input.policy.demoFirst
      || input.preparation.domainId !== "develop"
      || input.preparation.overlays.some((overlay) => overlay.id === input.overlayId)) {
    throw new DomainExecutionError("DOMAIN_EXECUTION_OVERLAY_INCOMPATIBLE", input.overlayId)
  }
  const current = input.preparation
  return {
    schemaVersion: current.schemaVersion,
    domainId: current.domainId,
    mode: current.mode,
    goal: current.goal,
    workspace: current.workspace,
    instructions: [
      ...current.instructions,
      "Use a reviewed WorkGraph; the Hackathon overlay does not authorize direct execution.",
      "Put the smallest demonstrable vertical slice first while preserving GoalContract coverage and verifier gates.",
    ],
    allowedOperations: [...current.allowedOperations],
    allowedSubagentTypes: [...current.allowedSubagentTypes],
    overlays: [...current.overlays, { id: input.overlayId, revision: input.overlayRevision }],
    skills: (current.skills ?? []).map((skill) => ({ ...skill })),
    environment: { ...current.environment },
  }
}

function hackathonProposal(input: DomainOverlayProposalInput): DomainExecutionProposal {
  const bound = input.binding.overlays.find((overlay) => overlay.overlayId === input.overlayId)
  if (input.overlayId !== "hackathon" || input.binding.selection.domain !== "develop"
      || !bound || bound.overlayRevision !== input.overlayRevision
      || !input.preparation.overlays.some(
        (overlay) => overlay.id === input.overlayId && overlay.revision === input.overlayRevision,
      )) {
    throw new DomainExecutionError("DOMAIN_EXECUTION_OVERLAY_INCOMPATIBLE", input.overlayId)
  }
  if (input.proposal.kind !== "work_graph") {
    throw new DomainExecutionError("DOMAIN_PROPOSAL_FORBIDDEN", "hackathon requires WorkGraph")
  }
  const graph: WorkGraph = {
    units: input.proposal.graph.units.map((unit) => ({
      ...unit,
      claimIds: [...unit.claimIds],
      criterionIds: [...unit.criterionIds],
      dependsOn: [...unit.dependsOn],
      readSet: [...unit.readSet],
      writeSet: [...unit.writeSet],
      integrationRequests: [...unit.integrationRequests],
    })),
    integrationPaths: [...input.proposal.graph.integrationPaths],
  }
  const root = graph.units.findIndex((unit) => unit.dependsOn.length === 0)
  if (root > 0) graph.units.unshift(...graph.units.splice(root, 1))
  return { kind: "work_graph", graph }
}

/** Hackathon composes planning behavior around Develop; it is not a third Domain executor. */
export const hackathonExecutionOverlay: DomainExecutionOverlayModule = Object.freeze({
  id: "hackathon-overlay-default",
  revision: "1",
  overlayId: "hackathon",
  compatibleDomains: Object.freeze(["develop"]),
  preparation: Object.freeze({
    id: "hackathon-context",
    revision: "1",
    apply: (input: ReadonlyValue<DomainOverlayPreparationInput>) =>
      hackathonPreparation(input as DomainOverlayPreparationInput),
  }),
  proposal: Object.freeze({
    id: "hackathon-demo-first",
    revision: "1",
    apply: (input: ReadonlyValue<DomainOverlayProposalInput>) =>
      hackathonProposal(input as DomainOverlayProposalInput),
  }),
})

type StrategyInvalidCode = "DOMAIN_EXECUTION_MODULE_INVALID" | "DOMAIN_EXECUTION_OVERLAY_INVALID"

/**
 * Capture all observable strategy state without invoking accessors. Stable
 * reference IDs make replacement detectable while recursive serialization
 * also catches in-place mutation of objects, collections, and prototypes.
 * JavaScript does not expose closure cells or class private slots; those remain
 * part of the trusted registration implementation and must be immutable.
 */
function strategyStateGuard(
  strategy: object,
  method: PropertyKey,
  invalidCode: StrategyInvalidCode,
): () => void {
  const references = new WeakMap<object, number>()
  const symbols = new Map<symbol, number>()
  let nextReference = 0
  let nextSymbol = 0
  const reference = (value: object) => {
    let id = references.get(value)
    if (id === undefined) {
      id = ++nextReference
      references.set(value, id)
    }
    return id
  }
  const symbol = (value: symbol) => {
    let id = symbols.get(value)
    if (id === undefined) {
      id = ++nextSymbol
      symbols.set(value, id)
    }
    return id
  }
  const key = (value: PropertyKey) => typeof value === "symbol" ? `y${symbol(value)}` : `s${JSON.stringify(value)}`
  const primitive = (value: unknown): string => {
    if (value === null) return "null"
    switch (typeof value) {
      case "undefined": return "undefined"
      case "boolean": return value ? "true" : "false"
      case "string": return `string:${JSON.stringify(value)}`
      case "bigint": return `bigint:${value}`
      case "symbol": return `symbol:${symbol(value)}`
      case "number":
        if (Number.isNaN(value)) return "number:NaN"
        if (Object.is(value, -0)) return "number:-0"
        return `number:${value}`
      default: return ""
    }
  }
  const serialize = (value: unknown, visiting: Set<object>, omitted?: PropertyKey): string => {
    if ((typeof value !== "object" || value === null) && typeof value !== "function") return primitive(value)
    if (typeof value === "function") return `function:${reference(value)}`
    if (value instanceof WeakMap || value instanceof WeakSet || value instanceof Promise) {
      throw new DomainExecutionError(invalidCode, "strategy has opaque mutable state")
    }
    const id = reference(value)
    if (visiting.has(value)) return `reference:${id}`
    visiting.add(value)
    try {
      const prototype = Object.getPrototypeOf(value) as object | null
      const parts = [`object:${id}`, `prototype:${prototype === null ? "null" : reference(prototype)}`]
      if (value instanceof Date) parts.push(`date:${value.getTime()}`)
      if (value instanceof RegExp) parts.push(`regexp:${value.source}/${value.flags}/${value.lastIndex}`)
      if (value instanceof Map) {
        parts.push("map:" + [...Map.prototype.entries.call(value)]
          .map(([entryKey, entryValue]) => `${serialize(entryKey, visiting)}=>${serialize(entryValue, visiting)}`)
          .join(","))
      }
      if (value instanceof Set) {
        parts.push("set:" + [...Set.prototype.values.call(value)]
          .map((entry) => serialize(entry, visiting)).join(","))
      }
      if (value instanceof ArrayBuffer || ArrayBuffer.isView(value)) {
        const bytes = value instanceof ArrayBuffer
          ? new Uint8Array(value)
          : new Uint8Array(value.buffer, value.byteOffset, value.byteLength)
        parts.push(`bytes:${[...bytes].join(".")}`)
      }
      const keys = Reflect.ownKeys(value).filter((entry) => entry !== omitted)
      for (const property of keys) {
        const descriptor = Object.getOwnPropertyDescriptor(value, property)!
        const flags = `${descriptor.enumerable ? 1 : 0}${descriptor.configurable ? 1 : 0}`
        if ("value" in descriptor) {
          parts.push(`${key(property)}:${flags}${descriptor.writable ? 1 : 0}:${serialize(descriptor.value, visiting)}`)
        } else {
          parts.push(`${key(property)}:${flags}:accessor:${serialize(descriptor.get, visiting)}:${serialize(descriptor.set, visiting)}`)
        }
      }
      if (prototype !== null) {
        parts.push("prototype-state:" + Reflect.ownKeys(prototype).map((property) => {
          const descriptor = Object.getOwnPropertyDescriptor(prototype, property)!
          if ("value" in descriptor) return `${key(property)}:${serialize(descriptor.value, visiting)}`
          return `${key(property)}:${serialize(descriptor.get, visiting)}:${serialize(descriptor.set, visiting)}`
        }).join(","))
      }
      return parts.join("|")
    } finally {
      visiting.delete(value)
    }
  }
  const snapshot = serialize(strategy, new Set(), method)
  return () => {
    if (serialize(strategy, new Set(), method) !== snapshot) {
      throw new DomainExecutionError(invalidCode, "strategy state changed after registration")
    }
  }
}

/** Plain descriptors run against a detached receiver. Class receivers are kept
 * for private-field compatibility, with observable state checked before and
 * after every call. In both cases the original entry point is pinned.
 */
export function pinStrategy<T extends StrategyIdentity, K extends keyof T>(
  strategy: T,
  method: K,
  invalidCode: StrategyInvalidCode,
): T {
  const prototype = Object.getPrototypeOf(strategy)
  const callback = strategy[method] as (...args: unknown[]) => unknown
  const receiver = prototype === Object.prototype || prototype === null
    ? Object.freeze({ ...strategy, id: strategy.id, revision: strategy.revision, [method]: callback })
    : strategy
  const assertUnchanged = strategyStateGuard(receiver, method, invalidCode)
  const guarded = (...args: unknown[]) => {
    assertUnchanged()
    try {
      return Reflect.apply(callback, receiver, args)
    } finally {
      assertUnchanged()
    }
  }
  return Object.freeze({ ...strategy, id: strategy.id, revision: strategy.revision, [method]: guarded })
}

export function pinDomainExecutionModule(module: DomainExecutionModule): DomainExecutionModule {
  return Object.freeze({
    id: module.id, revision: module.revision, domainId: module.domainId,
    preparation: pinStrategy(module.preparation, "prepare", "DOMAIN_EXECUTION_MODULE_INVALID"),
    proposal: pinStrategy(module.proposal, "normalize", "DOMAIN_EXECUTION_MODULE_INVALID"),
  })
}

export function pinDomainExecutionOverlay(overlay: DomainExecutionOverlayModule): DomainExecutionOverlayModule {
  return Object.freeze({
    id: overlay.id, revision: overlay.revision, overlayId: overlay.overlayId,
    compatibleDomains: Object.freeze([...overlay.compatibleDomains]),
    preparation: pinStrategy(overlay.preparation, "apply", "DOMAIN_EXECUTION_OVERLAY_INVALID"),
    proposal: pinStrategy(overlay.proposal, "apply", "DOMAIN_EXECUTION_OVERLAY_INVALID"),
  })
}

export class DomainExecutionRegistry implements DomainExecutionModuleResolver {
  readonly #modules = new Map<string, DomainExecutionModule>()
  readonly #overlays = new Map<string, DomainExecutionOverlayModule>()

  constructor(
    modules: readonly DomainExecutionModule[],
    overlays: readonly DomainExecutionOverlayModule[] = [],
  ) {
    if (!Array.isArray(modules) || !Array.isArray(overlays)) {
      throw new DomainExecutionError("DOMAIN_EXECUTION_MODULE_INVALID")
    }
    for (const module of modules) {
      if (!module || !identifier(module.id) || !identifier(module.revision) || !identifier(module.domainId)
          || !identifier(module.preparation?.id) || !identifier(module.preparation?.revision)
          || typeof module.preparation?.prepare !== "function"
          || !identifier(module.proposal?.id) || !identifier(module.proposal?.revision)
          || typeof module.proposal?.normalize !== "function") {
        throw new DomainExecutionError("DOMAIN_EXECUTION_MODULE_INVALID")
      }
      if (this.#modules.has(module.domainId)) {
        throw new DomainExecutionError("DOMAIN_EXECUTION_MODULE_DUPLICATE", module.domainId)
      }
      // Capture executable references as well as identities. A caller may retain
      // and edit its registration object while runs are using this registry.
      this.#modules.set(module.domainId, pinDomainExecutionModule(module))
    }
    for (const overlay of overlays) {
      if (!overlay || !identifier(overlay.id) || !identifier(overlay.revision) || !identifier(overlay.overlayId)
          || !Array.isArray(overlay.compatibleDomains) || overlay.compatibleDomains.length === 0
          || overlay.compatibleDomains.some((domain: string) => !identifier(domain))
          || new Set(overlay.compatibleDomains).size !== overlay.compatibleDomains.length
          || !identifier(overlay.preparation?.id) || !identifier(overlay.preparation?.revision)
          || typeof overlay.preparation?.apply !== "function"
          || !identifier(overlay.proposal?.id) || !identifier(overlay.proposal?.revision)
          || typeof overlay.proposal?.apply !== "function") {
        throw new DomainExecutionError("DOMAIN_EXECUTION_OVERLAY_INVALID")
      }
      if (this.#overlays.has(overlay.overlayId)) {
        throw new DomainExecutionError("DOMAIN_EXECUTION_OVERLAY_DUPLICATE", overlay.overlayId)
      }
      this.#overlays.set(overlay.overlayId, pinDomainExecutionOverlay(overlay))
    }
  }

  resolve(domainId: string) {
    const module = this.#modules.get(domainId)
    if (!module) throw new DomainExecutionError("DOMAIN_EXECUTION_MODULE_UNREGISTERED", domainId)
    return module
  }

  resolveOverlay(overlayId: string) {
    const overlay = this.#overlays.get(overlayId)
    if (!overlay) throw new DomainExecutionError("DOMAIN_EXECUTION_OVERLAY_UNREGISTERED", overlayId)
    return overlay
  }
}

export const builtinDomainExecutionRegistry = new DomainExecutionRegistry([
  generalExecutionModule,
  developExecutionModule,
], [hackathonExecutionOverlay])
