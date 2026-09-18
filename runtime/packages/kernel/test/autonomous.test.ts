import { describe, expect, test } from "bun:test"
import type {
  ActionGate, AuthorityGrant, DecisionProposal, ObservationReport, SubjectRef, VersionRef,
} from "@base-harness/domain-contracts"
import {
  admitDecision, assertAutonomousSchema, authorityAllows, canonicalJson, evaluateActionGate,
  parseDecisionProposal, parseObservationReport, scopeContains, validateAuthority, validateBudgetLimits,
  type DecisionAdmissionContext,
} from "../src/index"

const now = Date.parse("2026-09-18T00:00:10Z")
const ref = (id: string, revision = 1): VersionRef => ({ id, revision, sha256: "a".repeat(64) })
const report: SubjectRef & { kind: "report" } = { ...ref("report"), kind: "report" }
const source: SubjectRef = { ...ref("file"), kind: "source" }
const grant: AuthorityGrant = {
  schemaVersion: "authority-v1", ref: ref("grant"), runId: "run", provenanceRefs: [{ sourceId: "user", sha256: "b".repeat(64) }],
  capabilities: [{ operation: "read", targets: [{ kind: "workspace_path", selector: "/work" }],
    exclusions: [{ kind: "workspace_path", selector: "/work/private" }] }], expiresAt: "2026-09-18T01:00:00Z",
}
const basis = { runId: "run", taskId: "task", taskRevision: 1, intentRef: ref("intent"), interpretationRef: ref("interpretation"), authorityRef: grant.ref }
const read: DecisionProposal = {
  schemaVersion: "decision-v1", decisionId: "read-1", basis, observationIds: [],
  action: { kind: "invoke", toolId: "read", arguments: { filePath: "/work/file" } },
}
const failed: ObservationReport = {
  schemaVersion: "observation-v1", observationId: "obs", requestId: "measurement", runId: "run", taskId: "task", subject: source,
  checkRef: ref("test"), environmentHash: "c".repeat(64), startedAt: "2026-09-18T00:00:00Z", finishedAt: "2026-09-18T00:00:01Z",
  producer: { kind: "verifier", id: "python", revision: "5" },
  result: { execution: "completed", findings: [{ kind: "comparison", name: "exit_code", operator: "equals", expected: 0, observed: 1, result: "fail" }] },
  artifacts: [], limitations: [],
}
const gate: ActionGate = {
  id: "required-test", source: "explicit_user", sourceRefs: grant.provenanceRefs, action: "finish_satisfied",
  checkRef: failed.checkRef, requiredComparisons: ["exit_code"],
}
function finish(status: "satisfied" | "partial" | "not_assessed" = "partial"): DecisionProposal {
  return { ...read, decisionId: "finish", observationIds: ["obs"], action: {
    kind: "finish", report, openWork: "cancel", assessment: { status, summary: "Result", uncertainties: [], citedObservationIds: ["obs"] },
  } }
}
function context(proposal = read): DecisionAdmissionContext {
  return {
    basis, lifecycle: "active", now, authority: structuredClone(grant), observations: [structuredClone(failed)], subjects: [report, source],
    checks: [], gates: [], gateEvidence: { [gate.id]: { subject: source, environmentHash: failed.environmentHash } },
    supportedActions: ["invoke", "measure", "finish", "ask", "revise_interpretation"],
    resolvedAction: { canonicalAction: canonicalJson(proposal.action), effects: proposal.action.kind === "invoke" ?
      [{ operation: "read", targets: [{ kind: "workspace_path", selector: "/work/file" }] }] : [] },
  }
}

describe("autonomous wire contracts", () => {
  test("strict schema rejects actor authority, Ready and nested privilege fields", () => {
    for (const key of ["authorityGrant", "allowedOperations", "observations", "Ready", "permitId"]) {
      expect(() => parseDecisionProposal({ ...read, [key]: {} })).toThrow()
      expect(() => parseDecisionProposal({ ...read, basis: { ...basis, [key]: {} } })).toThrow()
    }
    expect(() => parseDecisionProposal({ ...read, action: { ...read.action, authorityGrant: grant } })).toThrow()
  })
  test("schema accepts opaque tool JSON, but it does not define effects", () => {
    const proposal = { ...read, action: { kind: "invoke", toolId: "custom", arguments: { operation: "read" } } }
    const ctx = context()
    ctx.resolvedAction = { canonicalAction: canonicalJson(proposal.action), effects: [{ operation: "execute", targets: [{ kind: "workspace_path", selector: "/work" }] }] }
    expect(admitDecision(proposal, ctx)).toEqual({ accepted: false, code: "AUTONOMOUS_OPERATION_FORBIDDEN" })
  })
  test("parsing returns detached data and canonical order ignores key insertion order", () => {
    const parsed = parseDecisionProposal(read)
    parsed.basis.taskRevision = 99
    expect(read.basis.taskRevision).toBe(1)
    expect(canonicalJson({ b: 2, a: 1 })).toBe(canonicalJson({ a: 1, b: 2 }))
  })
  test("JSON guard rejects getters without invoking them, cycles, holes and unsafe keys", () => {
    let invoked = false
    const getter = { get authority() { invoked = true; return grant } }
    const cyclic: Record<string, unknown> = {}; cyclic.self = cyclic
    for (const value of [getter, cyclic, [undefined], new Array(2), NaN, Infinity, new Date(), JSON.parse('{"__proto__":{}}')]) {
      expect(() => canonicalJson(value)).toThrow()
    }
    expect(invoked).toBe(false)
  })
  test("observations cannot carry a repair/Ready directive", () => {
    expect(parseObservationReport(failed).result.execution).toBe("completed")
    expect(() => parseObservationReport({ ...failed, outcome: "repair" })).toThrow()
    expect(() => parseObservationReport({ ...failed, result: { ...failed.result, readyEligible: true } })).toThrow()
    expect(() => parseObservationReport({ ...failed, finishedAt: "2026-09-17T00:00:00Z" })).toThrow()
  })
  test("report is not an apply candidate; model cannot allocate interpretation reference", () => {
    expect(() => parseDecisionProposal({ ...read, action: { kind: "apply_candidate", candidate: report } })).toThrow()
    expect(() => parseDecisionProposal({ ...read, action: { kind: "revise_interpretation", proposal: {
      schemaVersion: "interpretation-v1", ref: ref("forged"), basedOnRef: basis.interpretationRef, intentRef: basis.intentRef,
      goalSummary: "Changed hypothesis", assumptions: [], openQuestions: [], proposedCheckIds: [],
    } } })).toThrow()
  })
})

describe("pure autonomous admission", () => {
  test("the same failed observation allows investigation and partial completion", () => {
    expect(admitDecision({ ...read, observationIds: ["obs"] }, context()).accepted).toBe(true)
    expect(admitDecision(finish(), context(finish())).accepted).toBe(true)
  })
  test.each(["runId", "taskId", "taskRevision", "intentRef", "interpretationRef", "authorityRef"] as const)("rejects stale %s", (key) => {
    const changed = structuredClone(read)
    if (key === "runId" || key === "taskId") changed.basis[key] = "other"
    else if (key === "taskRevision") changed.basis[key]++
    else changed.basis[key].revision++
    expect(admitDecision(changed, context())).toEqual({ accepted: false, code: "AUTONOMOUS_STALE_BASIS" })
  })
  test.each(["preparing", "waiting_input", "closing", "closed"] as const)("does not dispatch during %s", (lifecycle) => {
    expect(admitDecision(read, { ...context(), lifecycle }).accepted).toBe(false)
  })
  test("waiting input may end partially without restarting execution", () => {
    expect(admitDecision(finish(), { ...context(finish()), lifecycle: "waiting_input" }).accepted).toBe(true)
  })
  test("cross-run and invented observations cannot be cited, including assessment citations", () => {
    expect(admitDecision(finish(), { ...context(finish()), observations: [{ ...failed, runId: "other" }] }).accepted).toBe(false)
    const proposal = finish(); if (proposal.action.kind === "finish") proposal.action.assessment.citedObservationIds.push("unknown")
    expect(admitDecision(proposal, context(proposal)).accepted).toBe(false)
  })
  test("stale report bytes and stale effect extraction are rejected", () => {
    const proposal = finish()
    expect(admitDecision(proposal, { ...context(proposal), subjects: [{ ...report, sha256: "d".repeat(64) }] }).accepted).toBe(false)
    expect(admitDecision(proposal, context()).accepted).toBe(false)
  })
  test("satisfied requires only explicit gates, partial remains possible", () => {
    const satisfied = finish("satisfied")
    expect(admitDecision(satisfied, context(satisfied)).accepted).toBe(true)
    expect(admitDecision(satisfied, { ...context(satisfied), gates: [gate] })).toEqual({ accepted: false, code: "AUTONOMOUS_GATE_UNSATISFIED" })
    expect(admitDecision(finish(), { ...context(finish()), gates: [gate] }).accepted).toBe(true)
  })
  test("empty gates, wrong subject/check/environment and newer errors cannot produce a pass", () => {
    const passed = structuredClone(failed)
    if (passed.result.execution === "completed" && passed.result.findings[0]?.kind === "comparison") passed.result.findings[0].result = "pass"
    const binding = context().gateEvidence[gate.id]!
    expect(evaluateActionGate(gate, binding, [passed], "run", now).state).toBe("met")
    for (const evidence of [undefined, { ...binding, subject: { ...source, revision: 2 } }, { ...binding, environmentHash: "changed" }]) {
      expect(evaluateActionGate(gate, evidence, [passed], "run", now).state).toBe("unknown")
    }
    expect(evaluateActionGate({ ...gate, requiredComparisons: [] }, binding, [passed], "run", now).state).toBe("unknown")
    expect(evaluateActionGate({ ...gate, checkRef: ref("test", 2) }, binding, [passed], "run", now).state).toBe("unknown")
    const tied = evaluateActionGate(gate, binding, [passed, { ...failed, observationId: "obs-tied" }], "run", now)
    expect(tied).toEqual({ gateId: gate.id, state: "unknown", observationIds: ["obs", "obs-tied"] })
    expect(evaluateActionGate(gate, binding, [passed, { ...failed, finishedAt: "2026-09-18T00:00:02Z", result: { execution: "not_run", reason: "Unavailable" } }], "run", now).state).toBe("unknown")
  })
  test("measurement must use registered subject-compatible check and declared effects", () => {
    const proposal: DecisionProposal = { ...read, action: { kind: "measure", checkRef: ref("test"), subject: source } }
    const ctx = context(proposal)
    expect(admitDecision(proposal, ctx).accepted).toBe(false)
    ctx.checks = [{ schemaVersion: "check-spec-v1", ref: ref("test"), author: "model", executorId: "python", parameters: {}, supportedSubjects: ["source"], requiredCapabilities: ["read"], timeoutMs: 1000 }]
    expect(admitDecision(proposal, ctx)).toEqual({ accepted: false, code: "AUTONOMOUS_EFFECT_INCOMPLETE" })
    ctx.resolvedAction.effects = context().resolvedAction.effects
    expect(admitDecision(proposal, ctx).accepted).toBe(true)
    expect(ctx.checks[0]!.author).toBe("model")
  })
})

describe("authority and resource invariants", () => {
  test("scope checks are segment-aware and reject uncanonical path aliases", () => {
    const parent = { kind: "workspace_path" as const, selector: "/work" }
    expect(scopeContains(parent, { ...parent, selector: "/work/file" })).toBe(true)
    for (const selector of ["/work-other/file", "/work/../secret", "/work//file", "/work/./file", "relative", "/work\\file"]) {
      expect(scopeContains(parent, { ...parent, selector })).toBe(false)
    }
    expect(authorityAllows(grant, "read", [{ ...parent, selector: "/work/private/key" }])).toBe(false)
    expect(authorityAllows(grant, "read", [parent])).toBe(false) // broad enumeration intersects exclusion
    expect(authorityAllows(grant, "read", [])).toBe(false)
  })
  test("child authority cannot extend scope, lifetime, operations or drop exclusions", () => {
    const child: AuthorityGrant = { ...structuredClone(grant), ref: ref("child"), parentRef: grant.ref }
    expect(() => validateAuthority(child, "run", now, grant)).not.toThrow()
    const dropped = structuredClone(child); dropped.capabilities[0]!.exclusions = []
    const widened = structuredClone(child); widened.capabilities[0]!.targets[0]!.selector = "/"
    const operation = structuredClone(child); operation.capabilities[0]!.operation = "mutate"
    for (const value of [dropped, widened, operation, { ...child, expiresAt: "2027-01-01T00:00:00Z" }]) {
      expect(() => validateAuthority(value, "run", now, grant)).toThrow()
    }
    const narrower = structuredClone(child); narrower.capabilities[0]!.targets[0]!.selector = "/work/public"; narrower.capabilities[0]!.exclusions = []
    expect(() => validateAuthority(narrower, "run", now, grant)).not.toThrow()
    expect(() => validateAuthority(child, "another-run", now, grant)).toThrow()
  })
  test("budgets require real finite limits and explicit metering capabilities", () => {
    const limits = { deadlineAt: "2026-09-18T01:00:00Z", maxActions: 10, maxParallelTasks: 2, maxTaskDepth: 0, maxTotalTasks: 1 }
    expect(() => validateBudgetLimits(limits, now, { tokens: false, cost: false })).not.toThrow()
    expect(() => validateBudgetLimits({ ...limits, maxModelTokens: 10 }, now, { tokens: false, cost: false })).toThrow("CAPABILITY")
    expect(() => validateBudgetLimits({ ...limits, maxCost: { currency: "USD", minorUnits: 10 } }, now, { tokens: false, cost: false })).toThrow("CAPABILITY")
    expect(() => validateBudgetLimits({ ...limits, maxActions: Infinity }, now, { tokens: true, cost: true })).toThrow()
    expect(() => assertAutonomousSchema("budget", { ...limits, maxActions: -1 })).toThrow()
  })
})
