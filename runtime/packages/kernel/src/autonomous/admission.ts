import type {
  ActionGate, AuthorityGrant, BudgetLimits, CheckSpec, DecisionAction, DecisionBasis,
  DecisionProposal, GateResult, ObservationReport, Operation, ResourceScope, RunLifecycle, SubjectRef, VersionRef,
} from "@base-harness/domain-contracts"
import { assertAutonomousSchema, canonicalJson, parseDecisionProposal } from "./schema"

export const sameRef = (a: VersionRef, b: VersionRef) =>
  a.id === b.id && a.revision === b.revision && a.sha256 === b.sha256
export const sameSubject = (a: SubjectRef, b: SubjectRef) => a.kind === b.kind && sameRef(a, b)

/** Adapters supply realpath/canonical resource identities, never unchecked user paths. */
export function validResourceScope(scope: ResourceScope): boolean {
  if (!scope.selector || /[\u0000-\u001f]/.test(scope.selector)) return false
  if (scope.kind === "external_resource") return true
  if (scope.kind === "network_origin") {
    try {
      const url = new URL(scope.selector)
      return ["http:", "https:"].includes(url.protocol) && url.origin === scope.selector
    } catch { return false }
  }
  if (scope.kind !== "workspace_path") return false
  const path = scope.selector
  return (/^\//.test(path) || /^[A-Za-z]:\//.test(path)) && !path.includes("\\") &&
    !path.includes("//") && !path.split("/").some((part) => part === "." || part === "..") &&
    (path === "/" || /^[A-Za-z]:\/$/.test(path) || !path.endsWith("/"))
}

export function scopeContains(parent: ResourceScope, child: ResourceScope): boolean {
  if (!validResourceScope(parent) || !validResourceScope(child) || parent.kind !== child.kind) return false
  if (parent.selector === child.selector) return true
  return parent.kind === "workspace_path" && child.selector.startsWith(parent.selector.replace(/\/$/, "") + "/")
}
const overlaps = (a: ResourceScope, b: ResourceScope) => scopeContains(a, b) || scopeContains(b, a)

export function authorityAllows(grant: AuthorityGrant, operation: Operation, targets: readonly ResourceScope[]): boolean {
  // Empty target lists cannot stand in for an unspecified resource footprint.
  return targets.length > 0 && targets.every((target) => grant.capabilities.some((capability) =>
    capability.operation === operation && capability.targets.some((allowed) => scopeContains(allowed, target)) &&
    !capability.exclusions.some((excluded) => overlaps(excluded, target)),
  ))
}

export function validateAuthority(grant: AuthorityGrant, runId: string, now: number, parent?: AuthorityGrant): void {
  assertAutonomousSchema("authority", grant)
  if (!Number.isFinite(now) || grant.runId !== runId || Date.parse(grant.expiresAt) <= now || !grant.provenanceRefs.length) {
    throw new Error("AUTONOMOUS_AUTHORITY_INVALID")
  }
  for (const capability of grant.capabilities) {
    if (!capability.targets.length || ![...capability.targets, ...capability.exclusions].every(validResourceScope)) {
      throw new Error("AUTONOMOUS_AUTHORITY_SCOPE")
    }
  }
  if (!parent) {
    if (grant.parentRef) throw new Error("AUTONOMOUS_AUTHORITY_PARENT_MISSING")
    return
  }
  assertAutonomousSchema("authority", parent)
  if (parent.runId !== runId || !grant.parentRef || !sameRef(grant.parentRef, parent.ref) ||
      Date.parse(grant.expiresAt) > Date.parse(parent.expiresAt)) throw new Error("AUTONOMOUS_AUTHORITY_ESCALATION")
  for (const child of grant.capabilities) {
    for (const target of child.targets) {
      const contained = parent.capabilities.some((allowed) => allowed.operation === child.operation &&
        allowed.targets.some((root) => scopeContains(root, target)) &&
        allowed.exclusions.every((excluded) => !overlaps(excluded, target) ||
          child.exclusions.some((kept) => scopeContains(kept, scopeContains(target, excluded) ? excluded : target))))
      if (!contained) throw new Error("AUTONOMOUS_AUTHORITY_ESCALATION")
    }
  }
}

export function validateBudgetLimits(limits: BudgetLimits, now: number, metering: { tokens: boolean; cost: boolean }): void {
  assertAutonomousSchema("budget", limits)
  if (!Number.isFinite(now) || Date.parse(limits.deadlineAt) <= now) throw new Error("AUTONOMOUS_DEADLINE_EXCEEDED")
  if ((limits.maxModelTokens !== undefined && !metering.tokens) || (limits.maxCost !== undefined && !metering.cost)) {
    throw new Error("AUTONOMOUS_BUDGET_CAPABILITY_UNSUPPORTED")
  }
}

export interface GateEvidence {
  /** Resolved by the Host from the protected action, not supplied by the model. */
  subject: SubjectRef
  environmentHash: string
  notBefore?: string
}

export function evaluateActionGate(
  gate: ActionGate, evidence: GateEvidence | undefined, observations: readonly ObservationReport[], runId: string, now: number,
): GateResult {
  assertAutonomousSchema("gate", gate)
  const unknown: GateResult = { gateId: gate.id, state: "unknown", observationIds: [] }
  if (!gate.sourceRefs.length || !gate.requiredComparisons.length || !evidence ||
      new Set(gate.requiredComparisons).size !== gate.requiredComparisons.length || !Number.isFinite(now)) return unknown
  const cutoff = evidence.notBefore === undefined ? -Infinity : Date.parse(evidence.notBefore)
  if (Number.isNaN(cutoff)) return unknown
  // Use the latest exact observation; do not cherry-pick an older pass after a fail/error.
  const matches = observations.filter((o) => o.runId === runId && sameSubject(o.subject, evidence.subject) &&
    sameRef(o.checkRef, gate.checkRef) && o.environmentHash === evidence.environmentHash &&
    Date.parse(o.startedAt) >= cutoff && Date.parse(o.finishedAt) <= now)
  const latestAt = matches.reduce((value, item) => Math.max(value, Date.parse(item.finishedAt)), -Infinity)
  const latestMatches = matches.filter((item) => Date.parse(item.finishedAt) === latestAt)
  // Equal timestamps do not establish ordering. Never let insertion order
  // choose between contradictory (or merely duplicated) measurements.
  if (latestMatches.length !== 1) return { ...unknown, observationIds: latestMatches.map((item) => item.observationId).sort() }
  const latest = latestMatches[0]!
  if (latest.result.execution !== "completed") return { ...unknown, observationIds: [latest.observationId] }
  const findings = latest.result.findings
  const comparisons = gate.requiredComparisons.map((name) => findings.filter((f) => f.name === name))
  if (comparisons.some((list) => list.length !== 1 || list[0]!.kind !== "comparison")) {
    return { ...unknown, observationIds: [latest.observationId] }
  }
  const met = comparisons.every(([f]) => f?.kind === "comparison" && f.result === "pass")
  return { gateId: gate.id, state: met ? "met" : "unmet", observationIds: [latest.observationId] }
}

export interface ActionEffect {
  operation: Operation
  targets: ResourceScope[]
}

/** Trusted current runtime context. Never populated by spreading actor JSON. */
export interface DecisionAdmissionContext {
  basis: DecisionBasis
  lifecycle: RunLifecycle
  now: number
  authority: AuthorityGrant
  parentAuthority?: AuthorityGrant
  observations: readonly ObservationReport[]
  subjects: readonly SubjectRef[]
  checks: readonly CheckSpec[]
  gates: readonly ActionGate[]
  gateEvidence: Readonly<Record<string, GateEvidence>>
  supportedActions: readonly DecisionAction["kind"][]
  /** Effect extraction belongs to the registered tool/check adapter. */
  resolvedAction: { canonicalAction: string; effects: readonly ActionEffect[] }
}

export type DecisionAdmission =
  | { accepted: true; proposal: DecisionProposal; gates: GateResult[] }
  | { accepted: false; code: string }

/** Pure structural/invariant checks. Only Coordinator may reserve resources or mint permits. */
export function admitDecision(value: unknown, context: DecisionAdmissionContext): DecisionAdmission {
  const reject = (code: string): DecisionAdmission => ({ accepted: false, code })
  let proposal: DecisionProposal
  try { proposal = parseDecisionProposal(value) } catch { return reject("AUTONOMOUS_DECISION_SCHEMA") }
  const { basis, action } = proposal
  if (basis.runId !== context.basis.runId || basis.taskId !== context.basis.taskId ||
      basis.taskRevision !== context.basis.taskRevision || !sameRef(basis.intentRef, context.basis.intentRef) ||
      !sameRef(basis.interpretationRef, context.basis.interpretationRef) || !sameRef(basis.authorityRef, context.basis.authorityRef)) {
    return reject("AUTONOMOUS_STALE_BASIS")
  }
  if (context.lifecycle !== "active" && !(context.lifecycle === "waiting_input" && action.kind === "finish")) {
    return reject("AUTONOMOUS_RUN_NOT_ACTIVE")
  }
  try { validateAuthority(context.authority, basis.runId, context.now, context.parentAuthority) }
  catch { return reject("AUTONOMOUS_AUTHORITY_INVALID") }
  if (!sameRef(context.authority.ref, basis.authorityRef)) return reject("AUTONOMOUS_STALE_AUTHORITY")
  if (!context.supportedActions.includes(action.kind)) return reject("AUTONOMOUS_CAPABILITY_UNSUPPORTED")
  if (context.resolvedAction.canonicalAction !== canonicalJson(action)) return reject("AUTONOMOUS_EFFECT_BINDING")
  if (context.resolvedAction.effects.some((effect) => !authorityAllows(context.authority, effect.operation, effect.targets))) {
    return reject("AUTONOMOUS_OPERATION_FORBIDDEN")
  }
  const visible = new Set(context.observations.filter((o) => o.runId === basis.runId).map((o) => o.observationId))
  const observationIds = [...proposal.observationIds,
    ...(action.kind === "finish" ? action.assessment.citedObservationIds : []),
    ...(action.kind === "revise_interpretation" ? action.proposal.assumptions.flatMap((a) => a.observationIds) : []),
  ]
  if (observationIds.some((id) => !visible.has(id))) return reject("AUTONOMOUS_OBSERVATION_UNKNOWN")
  const subject = action.kind === "measure" ? action.subject : action.kind === "apply_candidate" ? action.candidate :
    action.kind === "finish" ? action.report : undefined
  if (subject && !context.subjects.some((s) => sameSubject(s, subject))) return reject("AUTONOMOUS_SUBJECT_STALE")
  if (action.kind === "measure") {
    const check = context.checks.find((c) => sameRef(c.ref, action.checkRef))
    if (!check || !check.supportedSubjects.includes(action.subject.kind)) return reject("AUTONOMOUS_CHECK_UNKNOWN")
    if (check.requiredCapabilities.some((op) => !context.resolvedAction.effects.some((effect) => effect.operation === op))) {
      return reject("AUTONOMOUS_EFFECT_INCOMPLETE")
    }
  }
  if (action.kind === "revise_interpretation") {
    if (!sameRef(action.proposal.basedOnRef, basis.interpretationRef) || !sameRef(action.proposal.intentRef, basis.intentRef)) {
      return reject("AUTONOMOUS_STALE_INTERPRETATION")
    }
    if (action.proposal.proposedCheckIds.some((id) => !context.checks.some((c) => c.ref.id === id))) {
      return reject("AUTONOMOUS_CHECK_UNKNOWN")
    }
  }
  const gateAction = action.kind === "apply_candidate" ? "apply_candidate" :
    action.kind === "finish" && action.assessment.status === "satisfied" ? "finish_satisfied" : undefined
  const gates: GateResult[] = []
  for (const gate of context.gates) {
    if (gate.action !== gateAction && !(gate.action === "external_publish" &&
        context.resolvedAction.effects.some((e) => e.operation === "publish"))) continue
    try { gates.push(evaluateActionGate(gate, context.gateEvidence[gate.id], context.observations, basis.runId, context.now)) }
    catch { return reject("AUTONOMOUS_GATE_INVALID") }
  }
  if (gates.some((g) => g.state !== "met")) return reject("AUTONOMOUS_GATE_UNSATISFIED")
  return { accepted: true, proposal, gates }
}
