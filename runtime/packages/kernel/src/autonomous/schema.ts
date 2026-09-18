import type { DecisionProposal, Json, ObservationReport } from "@base-harness/domain-contracts"

type Validator = (value: unknown) => boolean
const string: Validator = (v) => typeof v === "string"
const nonempty: Validator = (v) => typeof v === "string" && v.trim().length > 0
const integer: Validator = (v) => Number.isSafeInteger(v) && (v as number) >= 0
const positive: Validator = (v) => integer(v) && (v as number) > 0
const digest: Validator = (v) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v)
const timestamp: Validator = (v) => typeof v === "string" && Number.isFinite(Date.parse(v))
const oneOf = (...values: unknown[]): Validator => (v) => values.includes(v)
const array = (item: Validator): Validator => (v) => Array.isArray(v) && v.every(item)

// Wire data must be plain JSON. Reject accessors, prototypes, cycles, non-finite
// numbers and ambiguous values before a validator or canonicalizer touches them.
export function assertJson(value: unknown): asserts value is Json {
  const active = new Set<object>()
  let nodes = 0
  function visit(v: unknown, depth: number): void {
    if (++nodes > 100_000 || depth > 64) throw new Error("AUTONOMOUS_JSON_LIMIT")
    if (v === null || typeof v === "string" || typeof v === "boolean") return
    if (typeof v === "number" && Number.isFinite(v)) return
    if (!v || typeof v !== "object" || active.has(v)) throw new Error("AUTONOMOUS_JSON_INVALID")
    const proto = Object.getPrototypeOf(v)
    if (Array.isArray(v) ? proto !== Array.prototype : proto !== Object.prototype && proto !== null) {
      throw new Error("AUTONOMOUS_JSON_INVALID")
    }
    active.add(v)
    const descriptors = Object.getOwnPropertyDescriptors(v)
    if (Reflect.ownKeys(v).some((key) => typeof key !== "string")) throw new Error("AUTONOMOUS_JSON_INVALID")
    for (const [key, descriptor] of Object.entries(descriptors)) {
      if (Array.isArray(v) && key === "length") continue
      if (!("value" in descriptor) || !descriptor.enumerable || ["__proto__", "constructor", "prototype"].includes(key)) {
        throw new Error("AUTONOMOUS_JSON_INVALID")
      }
      if (Array.isArray(v) && !/^(0|[1-9][0-9]*)$/.test(key)) throw new Error("AUTONOMOUS_JSON_INVALID")
      visit(descriptor.value, depth + 1)
    }
    if (Array.isArray(v) && Object.keys(v).length !== v.length) throw new Error("AUTONOMOUS_JSON_INVALID")
    active.delete(v)
  }
  visit(value, 0)
}

export function canonicalJson(value: unknown): string {
  assertJson(value)
  const encode = (v: Json): string => {
    if (Array.isArray(v)) return `[${v.map(encode).join(",")}]`
    if (v !== null && typeof v === "object") {
      return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}:${encode(v[k]!)}`).join(",")}}`
    }
    return JSON.stringify(v)
  }
  return encode(value)
}

const object = (required: Record<string, Validator>, optional: Record<string, Validator> = {}): Validator => (v) => {
  if (!v || typeof v !== "object" || Array.isArray(v)) return false
  const record = v as Record<string, unknown>
  return Object.keys(record).every((key) => Object.hasOwn(required, key) || Object.hasOwn(optional, key)) &&
    Object.entries(required).every(([key, check]) => Object.hasOwn(record, key) && check(record[key])) &&
    Object.entries(optional).every(([key, check]) => !Object.hasOwn(record, key) || check(record[key]))
}

const refFields = { id: nonempty, revision: positive, sha256: digest }
const ref = object(refFields)
const subject = object({ ...refFields, kind: oneOf("source", "report", "candidate", "workspace", "resource_snapshot") })
const subjectKind = (kind: string) => object({ ...refFields, kind: oneOf(kind) })
const source = object({ sourceId: nonempty, sha256: digest })
const operation = oneOf("read", "search", "mutate", "execute", "delegate", "publish")
const scope = object({ kind: oneOf("workspace_path", "network_origin", "external_resource"), selector: nonempty })
const interpretationFields = {
  schemaVersion: oneOf("interpretation-v1"), intentRef: ref, goalSummary: nonempty,
  assumptions: array(object({ id: nonempty, statement: nonempty, observationIds: array(nonempty) })),
  openQuestions: array(nonempty), proposedCheckIds: array(nonempty),
}
const task = object({
  clientTaskKey: nonempty, objective: nonempty, requestedCapabilities: array(operation),
  dependsOn: array(object({ taskId: nonempty, when: oneOf("settled", "artifact_produced", "applied") })),
}, { requestedScopes: array(scope) })
const union = (...validators: Validator[]): Validator => (v) => validators.some((check) => check(v))
const assessment = object({
  status: oneOf("satisfied", "partial", "unsolved", "not_assessed"), summary: string,
  citedObservationIds: array(nonempty), uncertainties: array(nonempty),
})
const action = union(
  object({ kind: oneOf("invoke"), toolId: nonempty, arguments: () => true }),
  object({ kind: oneOf("measure"), checkRef: ref, subject }),
  object({ kind: oneOf("delegate"), tasks: array(task) }),
  object({ kind: oneOf("revise_interpretation"), proposal: object({ ...interpretationFields, basedOnRef: ref }) }),
  object({ kind: oneOf("amend_tasks"), expectedGraphRevision: positive, changes: array(union(
    object({ kind: oneOf("add"), task }),
    object({ kind: oneOf("replace_pending"), taskId: nonempty, task }),
    object({ kind: oneOf("cancel"), taskId: nonempty }),
  )) }),
  object({ kind: oneOf("ask"), reason: oneOf("information", "authority"), questions: (v) => array(nonempty)(v) && (v as unknown[]).length > 0 }),
  object({ kind: oneOf("apply_candidate"), candidate: subjectKind("candidate") }),
  object({ kind: oneOf("finish"), report: subjectKind("report"), assessment, openWork: oneOf("drain", "cancel") }),
)
const decisionBasis = object({ runId: nonempty, taskId: nonempty, taskRevision: positive, intentRef: ref, interpretationRef: ref, authorityRef: ref })
const decision = object({
  schemaVersion: oneOf("decision-v1"), decisionId: nonempty,
  basis: decisionBasis,
  observationIds: array(nonempty), action,
})
const finding = union(
  object({ kind: oneOf("value"), name: nonempty, observed: () => true }),
  object({ kind: oneOf("comparison"), name: nonempty, operator: oneOf("equals", "contains", "registered_comparator"),
    expected: () => true, observed: () => true, result: oneOf("pass", "fail") }),
)
const observation = object({
  schemaVersion: oneOf("observation-v1"), observationId: nonempty, requestId: nonempty, runId: nonempty, taskId: nonempty,
  subject, checkRef: ref, environmentHash: digest, startedAt: timestamp, finishedAt: timestamp,
  producer: object({ kind: oneOf("verifier"), id: nonempty, revision: nonempty }),
  result: union(
    object({ execution: oneOf("completed"), findings: array(finding) }),
    object({ execution: oneOf("not_run"), reason: nonempty }),
    object({ execution: oneOf("error"), error: object({ code: nonempty, message: string }), partialFindings: array(finding) }),
  ),
  artifacts: array(subject), limitations: array(nonempty),
})

/** Parsing proves shape only. The calling channel still determines provenance. */
export function parseDecisionProposal(value: unknown): DecisionProposal {
  assertJson(value)
  if (!decision(value)) throw new Error("AUTONOMOUS_DECISION_SCHEMA")
  return JSON.parse(canonicalJson(value)) as DecisionProposal
}

export function parseDecisionAction(value: unknown): DecisionProposal["action"] {
  assertJson(value)
  if (!action(value)) throw new Error("AUTONOMOUS_ACTION_SCHEMA")
  return JSON.parse(canonicalJson(value)) as DecisionProposal["action"]
}

/** Never call this on actor arguments and then treat the result as authenticated. */
export function parseObservationReport(value: unknown): ObservationReport {
  assertJson(value)
  if (!observation(value)) throw new Error("AUTONOMOUS_OBSERVATION_SCHEMA")
  const parsed = JSON.parse(canonicalJson(value)) as ObservationReport
  if (Date.parse(parsed.startedAt) > Date.parse(parsed.finishedAt)) throw new Error("AUTONOMOUS_OBSERVATION_TIME")
  return parsed
}

export const autonomousSchemas = {
  finalResponse: object({ kind: oneOf("final"), text: string, assessment, openWork: oneOf("drain", "cancel") }, { basedOn: decisionBasis }),
  subject,
  ref,
  authority: object({
    schemaVersion: oneOf("authority-v1"), ref, runId: nonempty, provenanceRefs: array(source),
    capabilities: array(object({ operation, targets: array(scope), exclusions: array(scope) })), expiresAt: timestamp,
  }, { parentRef: ref }),
  budget: object({ deadlineAt: timestamp, maxActions: positive, maxParallelTasks: positive, maxTaskDepth: integer, maxTotalTasks: positive }, {
    maxModelTokens: positive, maxCost: object({ currency: nonempty, minorUnits: integer }),
  }),
  gate: object({ id: nonempty, source: oneOf("explicit_user", "trusted_policy"), sourceRefs: array(source),
    action: oneOf("apply_candidate", "finish_satisfied", "external_publish"), checkRef: ref, requiredComparisons: array(nonempty) }),
  check: object({ schemaVersion: oneOf("check-spec-v1"), ref, author: oneOf("application", "user", "model"),
    executorId: nonempty, supportedSubjects: array(oneOf("source", "report", "candidate", "workspace", "resource_snapshot")),
    parameters: () => true, requiredCapabilities: array(operation), timeoutMs: positive }),
  intent: object({ schemaVersion: oneOf("intent-v1"), ref, originalRequest: subjectKind("source"),
    requirements: array(object({ id: nonempty, text: nonempty, sourceRefs: array(source) })),
    constraints: array(object({ id: nonempty, text: nonempty, sourceRefs: array(source) })),
  }),
  interpretation: object({ ...interpretationFields, ref }),
  preparation: union(
    object({ status: oneOf("proceed"), context: () => true }),
    object({ status: oneOf("needs_input"), reason: oneOf("information", "authority"), questions: (v) => array(nonempty)(v) && (v as unknown[]).length > 0 }),
    object({ status: oneOf("invalid"), code: nonempty }),
  ),
}

export function assertAutonomousSchema(name: keyof typeof autonomousSchemas, value: unknown): void {
  assertJson(value)
  if (!autonomousSchemas[name](value)) throw new Error(`AUTONOMOUS_${name.toUpperCase()}_SCHEMA`)
}
