export * as Orchestration from "./orchestration"

import { createHash } from "node:crypto"
import { constants as fsConstants, promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"

export type Phase =
  | "direct"
  | "exploration"
  | "planning"
  | "scheduling"
  | "implementation"
  | "worker_running"
  | "candidate_ready"
  | "scope_verifying"
  | "committing"
  | "integration"
  | "verification"
  | "root_verifying"
  | "repair"
  | "ready"
  | "blocked"
  | "interrupted"

export type ScopeKind = "root" | "exploration" | "work_unit" | "repair" | "integration" | "legacy"

export type WorkUnit = {
  id: string
  title: string
  instructions: string
  agentType?: string
  claimIds: string[]
  criterionIds: string[]
  dependsOn: string[]
  readSet: string[]
  writeSet: string[]
  integrationRequests: string[]
}

export type WorkGraph = {
  units: WorkUnit[]
  integrationPaths: string[]
}

export type ExplorationReport = {
  resolvedTargets: string[]
  dependencyEdges: string[]
  applicability: Record<string, string>
  risks: string[]
  unresolved: string[]
  sourceRefs: string[]
}

export type RepairDirective = {
  failureFingerprint: string
  claimIds: string[]
  criterionIds: string[]
  missingEvidence: string[]
  allowedPaths: string[]
  repairCount: number
}

export type WorkUnitResult = {
  workUnitId: string
  scopeId: string
  candidateId: string
  revision: number
  patchHash: string
  files: Array<{ path: string; beforeHash: string | null; afterHash: string }>
  integrationRequests: string[]
  scopeVerified: boolean
}

export type CandidateManifest = {
  candidateId: string
  runId: string
  scopeId: string
  workUnitId: string
  revision: number
  files: Array<{ path: string; beforeHash: string | null; afterHash: string }>
  patchHash: string
  overlayRoot: string
  candidateWorkspace?: string
}

export type CandidateAttestation = {
  candidateId: string
  candidateRevision: number
  patchHash: string
}

export class OrchestrationError extends Error {
  constructor(
    readonly code:
      | "WORKGRAPH_INVALID"
      | "WORKGRAPH_CONFLICT"
      | "OWNERSHIP_VIOLATION"
      | "WORKSPACE_CONFLICT"
      | "PHASE_VIOLATION"
      | "PARALLEL_LIMIT",
    message: string,
  ) {
    super(message)
    this.name = "OrchestrationError"
  }
}

type UnitState = WorkUnit & {
  readRoots: string[]
  writeRoots: string[]
  status: "pending" | "queued" | "running" | "candidate_ready" | "verifying" | "committing" | "completed" | "failed" | "repair_exhausted"
  sessionID?: string
}

type OverlayFile = {
  logical: string
  physical: string
  beforeHash: string | null
}

type ScopeState = {
  sessionID: string
  rootSessionID: string
  kind: ScopeKind
  workUnitId?: string
  status: "registered" | "running" | "candidate_ready" | "verifying" | "committing" | "completed" | "failed"
  overlayRoot?: string
  candidateRevision: number
  files: Map<string, OverlayFile>
  model?: { providerID: string; modelID: string; variant?: string }
}

type CandidateState = CandidateManifest & {
  scope: ScopeState
  root: RootState
}

type RootState = {
  sessionID: string
  workspace: string
  goal: string
  phase: Phase
  exploration: "adaptive" | "always" | "manual"
  maxParallelWorkUnits: number
  contractClaimIds: Set<string>
  contractCriterionIds: Set<string>
  graph?: { units: Map<string, UnitState>; integrationPaths: string[] }
  active: Set<string>
  completed: Set<string>
  model?: { providerID: string; modelID: string; variant?: string }
  stateDirectory: string
}

const roots = new Map<string, RootState>()
const scopes = new Map<string, ScopeState>()
const candidates = new Map<string, CandidateState>()
const readOnlyTools = new Set([
  "harness_contract",
  "harness_workgraph",
  "read",
  "glob",
  "grep",
  "webfetch",
  "websearch",
  "skill",
  "question",
  "todowrite",
  "lsp",
  "invalid",
  "plan_exit",
])
const workerTools = new Set(["read", "glob", "grep", "edit", "write", "lsp", "question", "invalid"])

const hash = (value: Uint8Array | string) => createHash("sha256").update(value).digest("hex")
const canonicalJSON = (value: unknown): string => {
  if (Array.isArray(value)) return `[${value.map(canonicalJSON).join(",")}]`
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJSON(record[key])}`)
      .join(",")}}`
  }
  return JSON.stringify(value) ?? "null"
}
const safeID = (value: string) => value.replace(/[^A-Za-z0-9_.-]/g, "_")
const platformPath = (value: string) => (process.platform === "win32" ? value.toLowerCase() : value)
const inside = (parent: string, child: string) => {
  const relative = path.relative(platformPath(parent), platformPath(child))
  return relative === "" || (!relative.startsWith(".." + path.sep) && relative !== ".." && !path.isAbsolute(relative))
}
const overlaps = (left: string, right: string) => inside(left, right) || inside(right, left)

const stateBase = () => {
  if (process.platform === "win32") return path.join(process.env.LOCALAPPDATA ?? os.tmpdir(), "base-harness")
  return path.join(process.env.XDG_STATE_HOME ?? path.join(os.homedir(), ".local", "state"), "base-harness")
}

async function realpathCandidate(value: string): Promise<string> {
  let current = path.resolve(value)
  const suffix: string[] = []
  while (true) {
    try {
      return platformPath(path.join(await fs.realpath(current), ...suffix))
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error
      const parent = path.dirname(current)
      if (parent === current) throw error
      suffix.unshift(path.basename(current))
      current = parent
    }
  }
}

async function canonical(workspace: string, value: string): Promise<string> {
  if (/[?*\[\]]/.test(value)) {
    throw new OrchestrationError("WORKGRAPH_INVALID", `Ownership paths must be literal roots, not globs: ${value}`)
  }
  const root = await realpathCandidate(workspace)
  const candidate = await realpathCandidate(path.isAbsolute(value) ? value : path.resolve(workspace, value))
  if (!inside(root, candidate)) {
    throw new OrchestrationError("OWNERSHIP_VIOLATION", `Path escapes the workspace: ${value}`)
  }
  return candidate
}

function rootFor(sessionID: string) {
  const direct = roots.get(sessionID)
  if (direct) return direct
  const scope = scopes.get(sessionID)
  return scope ? roots.get(scope.rootSessionID) : undefined
}

function snapshotValue(root: RootState) {
  return {
    sessionID: root.sessionID,
    workspace: root.workspace,
    goal: root.goal,
    phase: root.phase,
    maxParallelWorkUnits: root.maxParallelWorkUnits,
    contractClaimIds: [...root.contractClaimIds],
    contractCriterionIds: [...root.contractCriterionIds],
    activeScopeIds: [...root.active],
    completedScopeIds: [...root.completed],
    model: root.model,
    units: root.graph
      ? [...root.graph.units.values()].map(({ readRoots: _read, writeRoots: _write, ...unit }) => unit)
      : [],
    candidates: [...candidates.values()]
      .filter((candidate) => candidate.runId === root.sessionID)
      .map(({ scope: _scope, root: _root, ...candidate }) => candidate),
    integrationPaths: root.graph?.integrationPaths ?? [],
    updatedAt: new Date().toISOString(),
  }
}

function persist(root: RootState) {
  const body = JSON.stringify(snapshotValue(root), null, 2)
  void fs
    .mkdir(root.stateDirectory, { recursive: true })
    .then(() => fs.writeFile(path.join(root.stateDirectory, "orchestration.json"), body, "utf8"))
}

function uncertain(goal: string) {
  const explicitFile =
    /(?:^|\s)[\w@./\\-]+\.(?:ts|tsx|js|jsx|py|rs|go|java|kt|cs|cpp|c|h|md|json|jsonc|toml|ya?ml)(?:\s|$)/i.test(
      goal,
    )
  const broad =
    /(?:구조|전체|병렬|리팩터|마이그레이션|계획|영향|모듈|패키지|architecture|parallel|refactor|migration|implement this plan)/i.test(
      goal,
    )
  const implementationIntent =
    /(?:만들|구현|수정|변경|추가|제거|개선|코드|파일|프로젝트|build|implement|create|fix|change|add|remove|update|code|project)/i.test(
      goal,
    )
  return broad || (!explicitFile && implementationIntent) || /(?:^|\n)\s*\d+\.\s+/m.test(goal) || goal.length > 600
}

function instruction(root: RootState) {
  if (root.phase === "direct") {
    return "Submit harness_contract before changing workspace state, then complete the explicit single-unit task directly."
  }
  return [
    "Base Harness orchestration is active.",
    "After discovery, submit harness_contract and then harness_workgraph.",
    "Assign every Claim to WorkUnits with literal readSet/writeSet module roots.",
    "The Host Coordinator launches accepted WorkUnits automatically; do not call task for implementation units.",
    "Workers may use structured read/edit/write tools only; shared files and shell commands belong to root integration.",
    "Verifier rejection must resume only the owning task_id and WorkUnit.",
  ].join("\n")
}

export function beginPrompt(input: {
  sessionID: string
  parentSessionID?: string
  workspace: string
  goal: string
  mode?: "adaptive" | "manual"
  exploration?: "adaptive" | "always" | "manual"
  maxParallelWorkUnits?: number
  model?: { providerID: string; modelID: string; variant?: string }
}) {
  const child = scopes.get(input.sessionID)
  if (child) {
    const root = roots.get(child.rootSessionID)
    if (root && (child.kind === "work_unit" || child.kind === "repair") && child.status === "completed") {
      child.kind = "repair"
      child.status = "registered"
      root.phase = "repair"
      const unit = child.workUnitId ? root.graph?.units.get(child.workUnitId) : undefined
      if (unit) unit.status = "pending"
      persist(root)
    }
    return { explore: false, instruction: "Repair only the assigned WorkUnit and its owned paths." }
  }

  const prior = roots.get(input.sessionID)
  if (prior && prior.phase !== "ready" && prior.phase !== "blocked" && prior.phase !== "interrupted") {
    return { explore: false, instruction: instruction(prior) }
  }

  const exploration = input.exploration ?? "adaptive"
  const explore =
    input.mode !== "manual" && (exploration === "always" || (exploration === "adaptive" && uncertain(input.goal)))
  const root: RootState = {
    sessionID: input.sessionID,
    workspace: path.resolve(input.workspace),
    goal: input.goal,
    phase: explore ? "exploration" : "direct",
    exploration,
    maxParallelWorkUnits: Math.max(1, Math.min(8, input.maxParallelWorkUnits ?? 2)),
    contractClaimIds: new Set(),
    contractCriterionIds: new Set(),
    active: new Set(),
    completed: new Set(),
    model: input.model,
    stateDirectory: path.join(stateBase(), "runs", safeID(input.sessionID)),
  }
  roots.set(input.sessionID, root)
  scopes.set(input.sessionID, {
    sessionID: input.sessionID,
    rootSessionID: input.sessionID,
    kind: "root",
    status: "running",
    candidateRevision: 0,
    files: new Map(),
    model: input.model,
  })
  persist(root)
  return {
    explore,
    instruction: instruction(root),
    explorationPrompt: [
      "Explore the workspace before planning this request.",
      "Use read-only tools only; shell, argv, edits, writes, and task delegation are forbidden.",
      "Return resolved targets, dependency edges, applicability, risks, unresolved questions, and source paths.",
      "User goal:",
      input.goal,
    ].join("\n"),
  }
}

export function registerContract(sessionID: string, claimIds: string[], criterionIds: string[]) {
  const root = rootFor(sessionID)
  if (!root) return
  root.contractClaimIds = new Set(claimIds)
  root.contractCriterionIds = new Set(criterionIds)
  persist(root)
}

export function hasContract(sessionID: string) {
  return (rootFor(sessionID)?.contractClaimIds.size ?? 0) > 0
}

export function canUseBeforeContract(sessionID: string, toolID: string) {
  return toolID === "task" && rootFor(sessionID)?.phase === "exploration"
}

async function validateGraph(root: RootState, graph: WorkGraph) {
  if (!graph.units.length) throw new OrchestrationError("WORKGRAPH_INVALID", "WorkGraph requires at least one WorkUnit")
  const ids = new Set(graph.units.map((unit) => unit.id))
  if (ids.size !== graph.units.length) throw new OrchestrationError("WORKGRAPH_INVALID", "Duplicate WorkUnit id")
  const byID = new Map(graph.units.map((unit) => [unit.id, unit]))
  for (const unit of graph.units) {
    if (!unit.id.trim() || !unit.title.trim() || !unit.instructions.trim() || !unit.claimIds.length || !unit.writeSet.length) {
      throw new OrchestrationError(
        "WORKGRAPH_INVALID",
        "Every WorkUnit needs id, title, instructions, Claim binding, and write ownership",
      )
    }
    if (unit.dependsOn.some((item) => !ids.has(item) || item === unit.id)) {
      throw new OrchestrationError("WORKGRAPH_INVALID", `Invalid dependency in WorkUnit ${unit.id}`)
    }
  }
  const visiting = new Set<string>()
  const visited = new Set<string>()
  const visit = (id: string) => {
    if (visiting.has(id)) throw new OrchestrationError("WORKGRAPH_INVALID", "WorkGraph contains a dependency cycle")
    if (visited.has(id)) return
    visiting.add(id)
    for (const dependency of byID.get(id)!.dependsOn) visit(dependency)
    visiting.delete(id)
    visited.add(id)
  }
  for (const id of ids) visit(id)

  const integrationPaths = await Promise.all(graph.integrationPaths.map((item) => canonical(root.workspace, item)))
  const units = new Map<string, UnitState>()
  for (const unit of graph.units) {
    if (
      unit.claimIds.some((item) => !root.contractClaimIds.has(item)) ||
      unit.criterionIds.some((item) => !root.contractCriterionIds.has(item))
    ) {
      throw new OrchestrationError("WORKGRAPH_INVALID", `WorkUnit ${unit.id} references unknown Claim or Criterion IDs`)
    }
    const readRoots = await Promise.all(unit.readSet.map((item) => canonical(root.workspace, item)))
    const writeRoots = await Promise.all(unit.writeSet.map((item) => canonical(root.workspace, item)))
    if (writeRoots.some((write) => integrationPaths.some((shared) => overlaps(write, shared)))) {
      throw new OrchestrationError("WORKGRAPH_CONFLICT", `WorkUnit ${unit.id} owns an integration-only path`)
    }
    units.set(unit.id, { ...unit, readRoots, writeRoots, status: "pending" })
  }
  const covered = new Set([...units.values()].flatMap((unit) => unit.claimIds))
  const missing = [...root.contractClaimIds].filter((claim) => !covered.has(claim))
  if (missing.length) throw new OrchestrationError("WORKGRAPH_INVALID", `Unassigned Claims: ${missing.join(", ")}`)

  const reaches = (from: string, target: string, seen = new Set<string>()): boolean => {
    if (seen.has(from)) return false
    seen.add(from)
    const dependencies = units.get(from)!.dependsOn
    return dependencies.includes(target) || dependencies.some((item) => reaches(item, target, seen))
  }
  const list = [...units.values()]
  for (let i = 0; i < list.length; i++) {
    for (let j = i + 1; j < list.length; j++) {
      const left = list[i]!
      const right = list[j]!
      const writeWrite = left.writeRoots.some((a) => right.writeRoots.some((b) => overlaps(a, b)))
      const readWrite =
        left.readRoots.some((a) => right.writeRoots.some((b) => overlaps(a, b))) ||
        right.readRoots.some((a) => left.writeRoots.some((b) => overlaps(a, b)))
      if ((writeWrite || readWrite) && !reaches(left.id, right.id) && !reaches(right.id, left.id)) {
        throw new OrchestrationError("WORKGRAPH_CONFLICT", `Parallel conflict between ${left.id} and ${right.id}`)
      }
    }
  }
  return { units, integrationPaths }
}

export async function acceptWorkGraph(sessionID: string, graph: WorkGraph) {
  const root = rootFor(sessionID)
  if (!root || root.sessionID !== sessionID) {
    throw new OrchestrationError("PHASE_VIOLATION", "Only the root may submit WorkGraph")
  }
  if (!root.contractClaimIds.size) {
    throw new OrchestrationError("PHASE_VIOLATION", "GoalContract must be accepted before WorkGraph")
  }
  if (root.phase !== "planning" && root.phase !== "exploration") {
    throw new OrchestrationError("PHASE_VIOLATION", `WorkGraph is not accepted during ${root.phase}`)
  }
  root.graph = await validateGraph(root, graph)
  root.phase = "scheduling"
  persist(root)
  return snapshotValue(root)
}

function assignment(scope: ScopeState, root: RootState) {
  const unit = scope.workUnitId ? root.graph?.units.get(scope.workUnitId) : undefined
  return {
    kind: scope.kind,
    rootSessionID: root.sessionID,
    workUnitId: scope.workUnitId,
    claimIds: unit?.claimIds ?? [],
    criterionIds: unit?.criterionIds ?? [],
  }
}

export function startChild(input: {
  parentSessionID: string
  sessionID: string
  subagentType: string
  workUnitId?: string
  model?: { providerID: string; modelID: string; variant?: string }
}) {
  const root = rootFor(input.parentSessionID)
  if (!root) return { kind: "legacy" as const, rootSessionID: input.parentSessionID, claimIds: [] as string[] }
  const prior = scopes.get(input.sessionID)
  if (prior?.status === "running") return assignment(prior, root)

  if (input.subagentType === "explore") {
    if (root.phase !== "exploration") {
      throw new OrchestrationError("PHASE_VIOLATION", "Exploration is allowed exactly once before planning")
    }
    const scope: ScopeState = {
      sessionID: input.sessionID,
      rootSessionID: root.sessionID,
      kind: "exploration",
      status: "running",
      candidateRevision: 0,
      files: new Map(),
      model: input.model,
    }
    scopes.set(input.sessionID, scope)
    root.active.add(input.sessionID)
    persist(root)
    return assignment(scope, root)
  }

  if (root.phase !== "scheduling" && root.phase !== "implementation" && root.phase !== "worker_running" && root.phase !== "repair") {
    throw new OrchestrationError("PHASE_VIOLATION", `Implementation task is not allowed during ${root.phase}`)
  }
  if (!input.workUnitId) {
    throw new OrchestrationError("WORKGRAPH_INVALID", "task requires work_unit_id under orchestration")
  }
  const unit = root.graph?.units.get(input.workUnitId)
  if (!unit) throw new OrchestrationError("WORKGRAPH_INVALID", `Unknown WorkUnit: ${input.workUnitId}`)
  const dependency = unit.dependsOn.find((id) => root.graph?.units.get(id)?.status !== "completed")
  if (dependency) throw new OrchestrationError("PHASE_VIOLATION", `WorkUnit ${unit.id} waits for ${dependency}`)
  if (root.active.size >= root.maxParallelWorkUnits) {
    throw new OrchestrationError(
      "PARALLEL_LIMIT",
      `At most ${root.maxParallelWorkUnits} WorkUnits may run concurrently`,
    )
  }
  if (prior && prior.workUnitId === unit.id && prior.status === "registered") {
    prior.kind = "repair"
    prior.status = "running"
    prior.model = input.model ?? prior.model
    unit.status = "running"
    unit.sessionID = input.sessionID
    root.active.add(input.sessionID)
    root.phase = "worker_running"
    persist(root)
    return assignment(prior, root)
  }
  unit.status = "running"
  unit.sessionID = input.sessionID
  const scope: ScopeState = {
    sessionID: input.sessionID,
    rootSessionID: root.sessionID,
    kind: root.phase === "repair" ? "repair" : "work_unit",
    workUnitId: unit.id,
    status: "running",
    candidateRevision: prior?.candidateRevision ?? 0,
    files: new Map(),
    model: input.model,
  }
  scopes.set(input.sessionID, scope)
  root.active.add(input.sessionID)
  root.phase = "worker_running"
  persist(root)
  return assignment(scope, root)
}

export function assertToolAllowed(sessionID: string, toolID: string, args?: unknown) {
  const scope = scopes.get(sessionID)
  const root = rootFor(sessionID)
  if (!root || !scope) return
  if (scope.kind === "exploration") {
    if (!readOnlyTools.has(toolID) || toolID === "harness_workgraph") {
      throw new OrchestrationError("PHASE_VIOLATION", `Exploration scope cannot use ${toolID}`)
    }
    return
  }
  if (scope.kind === "work_unit" || scope.kind === "repair") {
    if (!workerTools.has(toolID)) {
      throw new OrchestrationError(
        "PHASE_VIOLATION",
        `WorkUnit scope cannot use ${toolID}; shell/argv/apply_patch/task are root-only`,
      )
    }
    return
  }
  if (root.phase === "direct" || root.phase === "integration" || root.phase === "repair") return
  if (root.phase === "exploration" && (readOnlyTools.has(toolID) || toolID === "task")) return
  if (root.phase === "planning" && readOnlyTools.has(toolID)) return
  if (root.phase === "implementation" && (readOnlyTools.has(toolID) || toolID === "task")) return
  if (
    (root.phase === "verification" || root.phase === "ready" || root.phase === "blocked") &&
    readOnlyTools.has(toolID)
  )
    return
  void args
  throw new OrchestrationError("PHASE_VIOLATION", `${toolID} is not allowed during ${root.phase}`)
}

type DirectTarget = {
  kind: "direct"
  logicalPath: string
  physicalPath: string
  overlay: false
}

type ScopedTarget = {
  kind: "scoped"
  scope: ScopeState
  root: RootState
  logicalPath: string
}

async function targetFor(sessionID: string, workspace: string, value: string): Promise<DirectTarget | ScopedTarget> {
  const scope = scopes.get(sessionID)
  const root = rootFor(sessionID)
  const logical = path.isAbsolute(value) ? value : path.resolve(workspace, value)
  if (!scope || !root || scope.kind === "root" || scope.kind === "legacy") {
    return { kind: "direct", logicalPath: logical, physicalPath: logical, overlay: false }
  }
  return { kind: "scoped", scope, root, logicalPath: await canonical(root.workspace, logical) }
}

export async function resolveRead(sessionID: string, workspace: string, value: string) {
  const target = await targetFor(sessionID, workspace, value)
  if (target.kind === "direct") return target
  if (target.scope.kind === "exploration") {
    return { logicalPath: target.logicalPath, physicalPath: target.logicalPath, overlay: false }
  }
  const unit = target.scope.workUnitId ? target.root.graph?.units.get(target.scope.workUnitId) : undefined
  if (!unit || ![...unit.readRoots, ...unit.writeRoots].some((root) => inside(root, target.logicalPath))) {
    throw new OrchestrationError("OWNERSHIP_VIOLATION", `Read is outside WorkUnit ownership: ${target.logicalPath}`)
  }
  const mapped = target.scope.files.get(platformPath(target.logicalPath))
  return {
    logicalPath: target.logicalPath,
    physicalPath: mapped?.physical ?? target.logicalPath,
    overlay: Boolean(mapped),
  }
}

async function fileHash(filepath: string) {
  try {
    return hash(await fs.readFile(filepath))
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null
    throw error
  }
}

export async function resolveWrite(sessionID: string, workspace: string, value: string) {
  const target = await targetFor(sessionID, workspace, value)
  if (target.kind === "direct") return target
  if (target.scope.kind === "exploration") {
    throw new OrchestrationError("OWNERSHIP_VIOLATION", "Exploration is read-only")
  }
  const unit = target.scope.workUnitId ? target.root.graph?.units.get(target.scope.workUnitId) : undefined
  if (!unit || !unit.writeRoots.some((root) => inside(root, target.logicalPath))) {
    throw new OrchestrationError("OWNERSHIP_VIOLATION", `Write is outside WorkUnit ownership: ${target.logicalPath}`)
  }
  const key = platformPath(target.logicalPath)
  const prior = target.scope.files.get(key)
  if (prior) return { logicalPath: target.logicalPath, physicalPath: prior.physical, overlay: true }
  const overlayRoot =
    target.scope.overlayRoot ?? path.join(target.root.stateDirectory, "overlays", safeID(target.scope.sessionID))
  target.scope.overlayRoot = overlayRoot
  const relative = path.relative(platformPath(target.root.workspace), platformPath(target.logicalPath))
  const physical = path.join(overlayRoot, relative)
  await fs.mkdir(path.dirname(physical), { recursive: true })
  const beforeHash = await fileHash(target.logicalPath)
  if (beforeHash !== null) await fs.copyFile(target.logicalPath, physical)
  target.scope.files.set(key, { logical: target.logicalPath, physical, beforeHash })
  persist(target.root)
  return { logicalPath: target.logicalPath, physicalPath: physical, overlay: true }
}

const candidateHashPayload = (candidate: Omit<CandidateManifest, "candidateId" | "patchHash" | "overlayRoot">) => ({
  runId: candidate.runId,
  scopeId: candidate.scopeId,
  workUnitId: candidate.workUnitId,
  revision: candidate.revision,
  files: [...candidate.files].sort((left, right) => left.path.localeCompare(right.path)),
})

export async function prepareCandidate(sessionID: string): Promise<CandidateManifest | undefined> {
  const scope = scopes.get(sessionID)
  if (!scope?.workUnitId || (scope.kind !== "work_unit" && scope.kind !== "repair")) return
  const root = roots.get(scope.rootSessionID)
  const unit = root?.graph?.units.get(scope.workUnitId)
  if (!root || !unit) return
  const files: CandidateManifest["files"] = []
  for (const entry of scope.files.values()) {
    const content = await fs.readFile(entry.physical)
    files.push({ path: entry.logical, beforeHash: entry.beforeHash, afterHash: hash(content) })
  }
  const revision = scope.candidateRevision + 1
  const payload = candidateHashPayload({
    runId: root.sessionID,
    scopeId: scope.sessionID,
    workUnitId: scope.workUnitId,
    revision,
    files,
  })
  const patchHash = hash(canonicalJSON(payload))
  const candidateId = `${safeID(scope.sessionID)}-${revision}-${patchHash.slice(0, 16)}`
  const manifest: CandidateManifest = {
    candidateId,
    ...payload,
    patchHash,
    overlayRoot: scope.overlayRoot ?? path.join(root.stateDirectory, "overlays", safeID(scope.sessionID)),
  }
  scope.candidateRevision = revision
  scope.status = "candidate_ready"
  unit.status = "candidate_ready"
  root.phase = "candidate_ready"
  root.active.delete(sessionID)
  candidates.set(candidateId, { ...manifest, scope, root })
  persist(root)
  return manifest
}

export function markCandidateVerifying(candidateId: string) {
  const candidate = candidates.get(candidateId)
  if (!candidate) throw new OrchestrationError("PHASE_VIOLATION", `Unknown candidate: ${candidateId}`)
  candidate.scope.status = "verifying"
  candidate.root.graph?.units.get(candidate.workUnitId) &&
    (candidate.root.graph!.units.get(candidate.workUnitId)!.status = "verifying")
  candidate.root.phase = "scope_verifying"
  persist(candidate.root)
}

export async function materializeCandidate(candidateId: string): Promise<string> {
  const candidate = candidates.get(candidateId)
  if (!candidate) throw new OrchestrationError("PHASE_VIOLATION", `Unknown candidate: ${candidateId}`)
  if (candidate.candidateWorkspace) return candidate.candidateWorkspace
  const destination = path.resolve(candidate.root.stateDirectory, "candidates", safeID(candidateId), "workspace")
  if (!inside(path.resolve(candidate.root.stateDirectory), destination)) {
    throw new OrchestrationError("OWNERSHIP_VIOLATION", "Candidate workspace escaped the run state directory")
  }
  await fs.rm(destination, { recursive: true, force: true })
  const workspace = path.resolve(candidate.root.workspace)
  const stateDirectory = path.resolve(candidate.root.stateDirectory)
  await fs.cp(workspace, destination, {
    recursive: true,
    force: true,
    dereference: true,
    mode: fsConstants.COPYFILE_FICLONE,
    filter: async (source) => {
      const resolved = path.resolve(source)
      const relative = path.relative(workspace, resolved)
      if (relative === ".git" || relative.startsWith(`.git${path.sep}`)) return false
      if (inside(stateDirectory, resolved)) return false
      const stat = await fs.lstat(source)
      if (!stat.isSymbolicLink()) return true
      const target = await fs.realpath(source)
      if (!inside(workspace, target)) {
        throw new OrchestrationError("OWNERSHIP_VIOLATION", `Candidate materialization rejects external links: ${source}`)
      }
      return true
    },
  })
  for (const entry of candidate.scope.files.values()) {
    const relative = path.relative(platformPath(workspace), platformPath(entry.logical))
    const target = path.join(destination, relative)
    if (!inside(destination, target)) {
      throw new OrchestrationError("OWNERSHIP_VIOLATION", `Candidate file escaped materialized workspace: ${entry.logical}`)
    }
    const content = await fs.readFile(entry.physical)
    const expected = candidate.files.find((file) => file.path === entry.logical)?.afterHash
    if (!expected || hash(content) !== expected) {
      throw new OrchestrationError("WORKSPACE_CONFLICT", `Candidate changed during materialization: ${entry.logical}`)
    }
    await fs.mkdir(path.dirname(target), { recursive: true })
    await fs.writeFile(target, content)
  }
  candidate.candidateWorkspace = destination
  persist(candidate.root)
  return destination
}

export async function releaseCandidateWorkspace(candidateId: string) {
  const candidate = candidates.get(candidateId)
  if (!candidate?.candidateWorkspace) return
  const destination = candidate.candidateWorkspace
  const stateRoot = path.resolve(candidate.root.stateDirectory)
  if (!inside(stateRoot, path.resolve(destination))) {
    throw new OrchestrationError("OWNERSHIP_VIOLATION", "Candidate workspace escaped the run state directory")
  }
  await fs.rm(destination, { recursive: true, force: true })
  candidate.candidateWorkspace = undefined
  persist(candidate.root)
}

export async function commitCandidate(
  candidateId: string,
  attestation: CandidateAttestation,
): Promise<WorkUnitResult> {
  const candidate = candidates.get(candidateId)
  if (!candidate) throw new OrchestrationError("PHASE_VIOLATION", `Unknown candidate: ${candidateId}`)
  if (
    attestation.candidateId !== candidate.candidateId ||
    attestation.candidateRevision !== candidate.revision ||
    attestation.patchHash !== candidate.patchHash
  ) {
    throw new OrchestrationError("PHASE_VIOLATION", "Verifier attestation does not match the current candidate")
  }
  const { scope, root } = candidate
  const unit = root.graph?.units.get(candidate.workUnitId)
  if (!unit) throw new OrchestrationError("PHASE_VIOLATION", `Unknown WorkUnit: ${candidate.workUnitId}`)
  scope.status = "committing"
  unit.status = "committing"
  root.phase = "committing"
  persist(root)

  const entries = [...scope.files.values()].sort((left, right) => left.logical.localeCompare(right.logical))
  for (const entry of entries) {
    if ((await fileHash(entry.logical)) !== entry.beforeHash) {
      root.phase = "blocked"
      persist(root)
      throw new OrchestrationError(
        "WORKSPACE_CONFLICT",
        `Workspace changed while ${scope.workUnitId} was isolated: ${entry.logical}`,
      )
    }
  }

  const journal = path.join(root.stateDirectory, "journals", safeID(candidateId))
  const applied: Array<{ logical: string; backup?: string }> = []
  const temporary: string[] = []
  try {
    await fs.mkdir(journal, { recursive: true })
    for (const [index, entry] of entries.entries()) {
      const content = await fs.readFile(entry.physical)
      if (hash(content) !== candidate.files.find((item) => item.path === entry.logical)?.afterHash) {
        throw new OrchestrationError("WORKSPACE_CONFLICT", `Candidate content changed after verification: ${entry.logical}`)
      }
      await fs.mkdir(path.dirname(entry.logical), { recursive: true })
      const temp = `${entry.logical}.base-harness-${safeID(candidateId)}.tmp`
      temporary.push(temp)
      await fs.writeFile(temp, content)
      let backup: string | undefined
      if (entry.beforeHash !== null) {
        backup = path.join(journal, String(index))
        await fs.rename(entry.logical, backup)
      }
      try {
        await fs.rename(temp, entry.logical)
      } catch (error) {
        if (backup) await fs.rename(backup, entry.logical).catch(() => undefined)
        throw error
      }
      applied.push({ logical: entry.logical, backup })
    }
  } catch (error) {
    for (const item of applied.reverse()) {
      await fs.rm(item.logical, { force: true }).catch(() => undefined)
      if (item.backup) await fs.rename(item.backup, item.logical).catch(() => undefined)
    }
    for (const temp of temporary) await fs.rm(temp, { force: true }).catch(() => undefined)
    await fs.rm(journal, { recursive: true, force: true }).catch(() => undefined)
    root.phase = error instanceof OrchestrationError && error.code === "WORKSPACE_CONFLICT" ? "blocked" : "repair"
    scope.status = "failed"
    unit.status = "failed"
    persist(root)
    throw error
  }

  await fs.rm(journal, { recursive: true, force: true })
  if (scope.overlayRoot) await fs.rm(scope.overlayRoot, { recursive: true, force: true })
  scope.status = "completed"
  unit.status = "completed"
  root.completed.add(scope.sessionID)
  await releaseCandidateWorkspace(candidateId)
  candidates.delete(candidateId)
  root.phase = [...root.graph!.units.values()].every((item) => item.status === "completed")
    ? "integration"
    : "scheduling"
  persist(root)
  return {
    workUnitId: candidate.workUnitId,
    scopeId: scope.sessionID,
    candidateId,
    revision: candidate.revision,
    patchHash: candidate.patchHash,
    files: candidate.files,
    integrationRequests: unit.integrationRequests,
    scopeVerified: true,
  }
}

export async function discardCandidate(candidateId: string) {
  const candidate = candidates.get(candidateId)
  if (!candidate) return
  await releaseCandidateWorkspace(candidateId)
  if (candidate.scope.overlayRoot) await fs.rm(candidate.scope.overlayRoot, { recursive: true, force: true })
  candidate.scope.status = "failed"
  const unit = candidate.root.graph?.units.get(candidate.workUnitId)
  if (unit) unit.status = "failed"
  candidates.delete(candidateId)
  persist(candidate.root)
}

export function reopenScope(sessionID: string) {
  const scope = scopes.get(sessionID)
  const root = scope ? roots.get(scope.rootSessionID) : undefined
  const unit = scope?.workUnitId ? root?.graph?.units.get(scope.workUnitId) : undefined
  if (!scope || !root || !unit) throw new OrchestrationError("PHASE_VIOLATION", `Unknown repair scope: ${sessionID}`)
  for (const [candidateId, candidate] of candidates) {
    if (candidate.scopeId === sessionID) candidates.delete(candidateId)
  }
  scope.kind = "repair"
  scope.status = "registered"
  unit.status = "pending"
  root.phase = "repair"
  persist(root)
}

export async function finishChild(sessionID: string, success: boolean) {
  const scope = scopes.get(sessionID)
  if (!scope || scope.kind === "legacy" || scope.kind === "root") return
  const root = roots.get(scope.rootSessionID)
  if (!root) return
  root.active.delete(sessionID)
  if (scope.kind === "exploration") {
    scope.status = success ? "completed" : "failed"
    root.phase = success ? "planning" : "blocked"
    if (success) root.completed.add(sessionID)
    persist(root)
    return
  }
  const unit = scope.workUnitId ? root.graph?.units.get(scope.workUnitId) : undefined
  if (!success || !unit) {
    scope.status = "failed"
    if (unit) unit.status = "failed"
    root.phase = "repair"
    persist(root)
    return
  }
  try {
    return await prepareCandidate(sessionID)
  } catch (error) {
    scope.status = "failed"
    unit.status = "failed"
    root.phase = error instanceof OrchestrationError && error.code === "WORKSPACE_CONFLICT" ? "blocked" : "repair"
    persist(root)
    throw error
  }
}

export function requestVerification(sessionID: string) {
  const root = rootFor(sessionID)
  if (!root) return
  if (root.phase === "integration" || root.phase === "direct" || root.phase === "repair") root.phase = "root_verifying"
  persist(root)
}

export function markOutcome(sessionID: string, outcome: "ready" | "repair" | "blocked") {
  const root = rootFor(sessionID)
  if (!root) return
  root.phase = outcome
  persist(root)
}

export function markInterrupted(sessionID: string) {
  const root = rootFor(sessionID)
  if (!root) return
  root.phase = "interrupted"
  persist(root)
}

export function snapshot(sessionID: string) {
  const root = rootFor(sessionID)
  return root ? snapshotValue(root) : undefined
}

export function resetForTest() {
  roots.clear()
  scopes.clear()
  candidates.clear()
}
