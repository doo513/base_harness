import { createHash, randomUUID } from "node:crypto"
import { AsyncLocalStorage } from "node:async_hooks"
import { mkdir, mkdtemp, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import type {
  AuthorityGrant, AutonomousCoordinatorPort, AutonomousDomainModule, AutonomousPreparationInput,
  AutonomousResourceUsage, AutonomousRunPorts, AutonomousRunSetup, AutonomousRunSnapshot,
  BudgetLimits, CheckSpec, DecisionProposal, DomainExecutorSelection, IntentRecord, Json,
  SubjectRef, VersionRef, WorkingInterpretation,
} from "@base-harness/domain-contracts"
import { pinAutonomousDomainModule } from "@base-harness/domain"
import { assertAutonomousSchema, canonicalJson, parseDecisionAction, parseDecisionProposal, sameSubject, validateAuthority, validateBudgetLimits } from "@base-harness/kernel"

export interface StoredAutonomousSubject {
  subject: SubjectRef
  manifestJson: string
  /** Real logical origin when bytes came from an admitted file-read adapter. */
  origin?: string
}
export interface AutonomousHostInput {
  sessionID: string
  runId: string
  workspace: string
  goal: string
  domainId: string
  domainSnapshot: Json
  executor: DomainExecutorSelection
  context: unknown
}
export interface AutonomousHostOptions {
  modules: readonly AutonomousDomainModule[]
  artifactDirectory?: string
  limits(input: AutonomousHostInput): BudgetLimits
  metering: { tokens: boolean; cost: boolean }
  cleanupTimeoutMs: number
  /** Adapter must obtain these from existing user/policy permission services. */
  authorize(input: AutonomousHostInput): Promise<Pick<AuthorityGrant, "capabilities" | "provenanceRefs" | "expiresAt">>
  /** Answers are returned by the authenticated app question service, never actor JSON. */
  ask?(input: AutonomousHostInput & { questions: readonly string[]; signal: AbortSignal }): Promise<readonly (readonly string[])[]>
  adapter(input: AutonomousHostInput & {
    snapshotRoot: string
    subject(ref: SubjectRef): StoredAutonomousSubject
    check(ref: VersionRef): CheckSpec
    snapshot(): AutonomousRunSnapshot
  }): Promise<Omit<AutonomousRunPorts, "revise"> & {
    describeCheck?(parameters: Json, subject: StoredAutonomousSubject): Omit<CheckSpec, "schemaVersion" | "ref" | "author">
  }>
  checks?: CheckSpec[]
  gates?: AutonomousRunSetup["gates"]
  gateEvidence?: AutonomousRunSetup["gateEvidence"]
}

const digest = (value: string | Uint8Array) => createHash("sha256").update(value).digest("hex")
function version(id: string, revision: number, body: unknown): VersionRef {
  return { id, revision, sha256: digest(canonicalJson(body)) }
}
function frozen<T>(value: T): T {
  if (value && typeof value === "object") { for (const item of Object.values(value)) frozen(item); Object.freeze(value) }
  return value
}

/** Host-owned sources/strategy handles within an existing KernelHost SessionRecord.
 * Current lifecycle, grant, interpretation and budget remain Coordinator-owned.
 */
export class AutonomousHostRun {
  private readonly subjects = new Map<string, StoredAutonomousSubject>()
  private readonly checks = new Map<string, CheckSpec>()
  private readonly textFinals = new Map<string, { text: string; report: SubjectRef & { kind: "report" } }>()
  private readonly submissions = new Map<string, { fingerprint: string; result: Promise<import("@base-harness/domain-contracts").AutonomousDecisionResult> }>()
  private readonly userRevisions = new Map<string, Promise<import("@base-harness/domain-contracts").AutonomousPreparationResult>>()
  private readonly invocation = new AsyncLocalStorage<{ proposal: DecisionProposal; signal: AbortSignal; active: boolean }>()
  private describeCheck?: (parameters: Json, subject: StoredAutonomousSubject) => Omit<CheckSpec, "schemaVersion" | "ref" | "author">
  private ask?: AutonomousHostOptions["ask"]
  private questionRequest?: { controller: AbortController; result: Promise<import("@base-harness/domain-contracts").AutonomousPreparationResult> }
  readonly module: AutonomousDomainModule
  private constructor(
    readonly input: AutonomousHostInput,
    readonly snapshotRoot: string,
    module: AutonomousDomainModule,
    private readonly runtime: AutonomousCoordinatorPort,
    private readonly current: () => AutonomousRunSnapshot,
  ) { this.module = pinAutonomousDomainModule(module) }

  static async create(input: AutonomousHostInput, options: AutonomousHostOptions,
    runtime: AutonomousCoordinatorPort, current: () => AutonomousRunSnapshot) {
    const modules = options.modules.filter((module) => module.domainId === input.domainId)
    if (modules.length !== 1) throw new Error("AUTONOMOUS_DOMAIN_MODULE_UNREGISTERED_OR_DUPLICATE")
    const pinned = pinAutonomousDomainModule(modules[0]!)
    const limits = structuredClone(options.limits(input))
    validateBudgetLimits(limits, Date.now(), options.metering)
    const authorized = await options.authorize(input)
    const authorityBody = { schemaVersion: "authority-v1" as const, runId: input.runId, ...structuredClone(authorized) }
    const authority: AuthorityGrant = { ...authorityBody, ref: version("authority:" + randomUUID(), 1, authorityBody) }
    validateAuthority(authority, input.runId, Date.now())
    const directory = options.artifactDirectory ?? join(tmpdir(), "base-harness-autonomous-artifacts")
    await mkdir(directory, { recursive: true, mode: 0o700 })
    const root = await mkdtemp(join(directory, "run-"))
    const host = new AutonomousHostRun(input, root, pinned, runtime, current)
    host.ask = options.ask
    const original = await host.store("source", input.goal)
    const provenance = { sourceId: original.subject.id, sha256: digest(input.goal) }
    const intentBody = { schemaVersion: "intent-v1" as const, originalRequest: original.subject,
      requirements: [{ id: "user-request", text: input.goal, sourceRefs: [provenance] }], constraints: [] }
    const intent: IntentRecord = { ...intentBody, ref: version("intent:" + randomUUID(), 1, intentBody) }
    const explanation = { schemaVersion: "interpretation-v1" as const, intentRef: intent.ref, goalSummary: input.goal,
      assumptions: [], openQuestions: [], proposedCheckIds: [] }
    const interpretation: WorkingInterpretation = { ...explanation, ref: version("interpretation:" + randomUUID(), 1, explanation) }
    const domain = await host.store("resource_snapshot", canonicalJson({ metadata: input.domainSnapshot,
      strategy: { id: pinned.id, revision: pinned.revision, domainId: pinned.domainId } }))
    const executor = await host.store("resource_snapshot", canonicalJson(input.executor))
    const asRef = ({ id, revision, sha256 }: SubjectRef): VersionRef => ({ id, revision, sha256 })
    for (const check of options.checks ?? []) {
      assertAutonomousSchema("check", check)
      if (host.checks.has(check.ref.id)) throw new Error("AUTONOMOUS_CHECK_DUPLICATE")
      host.checks.set(check.ref.id, frozen(structuredClone(check)))
    }
    const setup: AutonomousRunSetup = {
      binding: { schemaVersion: "autonomous-run-binding-v1", semantics: "autonomous-v1", runId: input.runId,
        domainModule: asRef(domain.subject), executor: asRef(executor.subject), authorityRef: authority.ref, budgetId: input.runId + ":budget" },
      taskId: input.sessionID, intent, interpretation, authority, limits, metering: { ...options.metering },
      cleanupTimeoutMs: options.cleanupTimeoutMs, checks: [...host.checks.values()].map((v) => structuredClone(v)),
      gates: structuredClone(options.gates ?? []), gateEvidence: structuredClone(options.gateEvidence ?? {}),
      subjects: [...host.subjects.values()].map((value) => structuredClone(value.subject)),
    }
    const adapter = await options.adapter({ ...input, snapshotRoot: root, subject: (ref) => host.subject(ref),
      check: (ref) => host.check(ref), snapshot: current })
    host.describeCheck = adapter.describeCheck?.bind(adapter)
    const ports: AutonomousRunPorts = {
      ...adapter,
      cleanup: async () => {
        host.questionRequest?.controller.abort(new Error("AUTONOMOUS_QUESTION_CANCELLED"))
        return adapter.cleanup()
      },
      invoke: async (proposal, signal) => {
        const lease = { proposal, signal, active: true }
        try { return await host.invocation.run(lease, () => adapter.invoke(proposal, signal)) }
        finally { lease.active = false }
      },
      measure: async (proposal, signal) => {
        const lease = { proposal, signal, active: true }
        try { return await host.invocation.run(lease, () => adapter.measure(proposal, signal)) }
        finally { lease.active = false }
      },
      revise: ({ basedOnRef, ...proposal }) => ({ ...proposal, ref: version(basedOnRef.id, basedOnRef.revision + 1, proposal) }),
    }
    return { host, setup, ports }
  }

  snapshot(): AutonomousRunSnapshot {
    const current = this.current()
    if (current.binding.runId !== this.input.runId) throw new Error("AUTONOMOUS_RUN_MISMATCH")
    return current
  }

  async prepare() {
    const state = this.snapshot()
    const input: AutonomousPreparationInput = { originalRequest: this.input.goal, intent: state.intent,
      interpretation: state.interpretation, authority: state.authority, environment: { workspace: this.input.workspace } }
    const prepared = this.module.prepare(frozen(input))
    assertAutonomousSchema("preparation", prepared)
    await this.runtime.prepareAutonomous(this.input.sessionID, this.input.runId, prepared)
    return prepared
  }

  /** Takes no answer payload. Only the app-owned question port can supply a reply. */
  requestAnswers() {
    if (this.questionRequest) return this.questionRequest.result
    const state = this.snapshot()
    if (state.lifecycle !== "waiting_input" || !state.questions.length) throw new Error("AUTONOMOUS_QUESTION_STATE")
    if (!this.ask) throw new Error("AUTONOMOUS_QUESTION_SERVICE_UNAVAILABLE")
    const basedOn = this.runtime.autonomousBasis(this.input.sessionID, this.input.runId)
    const controller = new AbortController()
    const request = { controller, result: undefined as unknown as Promise<import("@base-harness/domain-contracts").AutonomousPreparationResult> }
    request.result = Promise.resolve().then(async () => {
      const { signal } = controller
      let onAbort!: () => void
      const cancelled = new Promise<never>((_, reject) => { onAbort = () => reject(signal.reason); signal.addEventListener("abort", onAbort, { once: true }) })
      let answers: readonly (readonly string[])[]
      try {
        signal.throwIfAborted()
        answers = await Promise.race([this.ask!({ ...this.input, questions: Object.freeze([...state.questions]), signal }), cancelled])
      } finally { signal.removeEventListener("abort", onAbort) }
      signal.throwIfAborted()
      const current = this.snapshot()
      if (current.lifecycle !== "waiting_input" || current.questionRevision !== state.questionRevision ||
          canonicalJson(this.runtime.autonomousBasis(this.input.sessionID, this.input.runId)) !== canonicalJson(basedOn)) {
        throw new Error("AUTONOMOUS_QUESTION_STALE")
      }
      if (!Array.isArray(answers) || answers.length !== state.questions.length || answers.some((answer) =>
        !Array.isArray(answer) || !answer.length || answer.some((text) => typeof text !== "string" || !text.trim()))) {
        throw new Error("AUTONOMOUS_ANSWER_SCHEMA")
      }
      const text = canonicalJson(state.questions.map((question, index) => ({ question, answers: answers[index] })))
      const source = await this.store("source", text)
      signal.throwIfAborted()
      this.runtime.registerAutonomousSubject(this.input.sessionID, this.input.runId, source.subject)
      const { ref: oldIntent, ...intentBody } = state.intent
      intentBody.requirements = [...intentBody.requirements, { id: source.subject.id, text,
        sourceRefs: [{ sourceId: source.subject.id, sha256: digest(text) }] }]
      const intent = { ...intentBody, ref: version(oldIntent.id, oldIntent.revision + 1, intentBody) }
      const { ref: oldInterpretation, ...interpretationBody } = state.interpretation
      interpretationBody.intentRef = intent.ref
      // Whether the answer resolves ambiguity remains a Domain/model judgement.
      const interpretation = { ...interpretationBody, ref: version(oldInterpretation.id, oldInterpretation.revision + 1, interpretationBody) }
      await this.runtime.resumeAutonomous(this.input.sessionID, this.input.runId, { basedOn, questionRevision: state.questionRevision, intent, interpretation })
      return this.prepare()
    }).finally(() => { if (this.questionRequest === request) this.questionRequest = undefined })
    this.questionRequest = request
    return request.result
  }

  /** App-owned user messages extend intent; they are never treated as actor decisions. */
  appendUserRequest(text: string, context: unknown) {
    const messageId = context && typeof context === "object" && typeof (context as { messageID?: unknown }).messageID === "string"
      ? (context as { messageID: string }).messageID : undefined
    if (!messageId || !text.trim()) throw new Error("AUTONOMOUS_USER_REVISION_SOURCE")
    const previous = this.userRevisions.get(messageId)
    if (previous) return previous
    let result: Promise<import("@base-harness/domain-contracts").AutonomousPreparationResult>
    result = Promise.resolve().then(async () => {
      const state = this.snapshot()
      if (state.lifecycle !== "active") throw new Error("AUTONOMOUS_INTENT_REVISION_STATE")
      const basedOn = this.runtime.autonomousBasis(this.input.sessionID, this.input.runId)
      const source = await this.store("source", text)
      this.runtime.registerAutonomousSubject(this.input.sessionID, this.input.runId, source.subject)
      const { ref: oldIntent, ...intentBody } = state.intent
      intentBody.requirements = [...intentBody.requirements, { id: source.subject.id, text,
        sourceRefs: [{ sourceId: source.subject.id, sha256: digest(text) }] }]
      const intent = { ...intentBody, ref: version(oldIntent.id, oldIntent.revision + 1, intentBody) }
      const { ref: oldInterpretation, ...interpretationBody } = state.interpretation
      interpretationBody.intentRef = intent.ref
      const interpretation = { ...interpretationBody,
        ref: version(oldInterpretation.id, oldInterpretation.revision + 1, interpretationBody) }
      await this.runtime.reviseAutonomousIntent(this.input.sessionID, this.input.runId, { basedOn, intent, interpretation })
      return this.prepare()
    }).catch((error) => {
      if (this.userRevisions.get(messageId) === result) this.userRevisions.delete(messageId)
      throw error
    })
    this.userRevisions.set(messageId, result)
    return result
  }

  submit(decisionId: string, response: unknown) {
    let fingerprint: string
    try { fingerprint = canonicalJson(response) } catch { return Promise.resolve({ accepted: false as const, code: "AUTONOMOUS_DECISION_SCHEMA" }) }
    const previous = this.submissions.get(decisionId)
    if (previous) return previous.fingerprint === fingerprint ? previous.result : Promise.resolve({ accepted: false as const, code: "AUTONOMOUS_REQUEST_CONFLICT" })
    const result = Promise.resolve().then(() => this.submitOnce(decisionId, response)).then((value) => frozen(structuredClone(value)))
    this.submissions.set(decisionId, { fingerprint, result })
    return result
  }

  assertInvocation(toolId: string, operation: string): void {
    const lease = this.invocation.getStore()
    const state = this.snapshot()
    const action = lease?.proposal.action
    const matches = action?.kind === "invoke" ? action.toolId === toolId : action?.kind === "measure" ?
      ["argv", "shell", "bash"].includes(toolId) && operation === "execute" && this.check(action.checkRef).requiredCapabilities.includes("execute") : false
    if (!lease?.active || lease.signal.aborted || state.lifecycle === "closed" || !matches ||
        canonicalJson(lease.proposal.basis.authorityRef) !== canonicalJson(state.authority.ref)) {
      throw new Error("AUTONOMOUS_ADMISSION_REQUIRED")
    }
  }

  private async submitOnce(decisionId: string, response: unknown) {
    this.snapshot()
    let textReport: (SubjectRef & { kind: "report" }) | undefined
    let finalBasis: import("@base-harness/domain-contracts").DecisionBasis | undefined
    let text = typeof response === "string" ? response : undefined
    if (response && typeof response === "object" && "kind" in response && response.kind === "final") {
      try { assertAutonomousSchema("finalResponse", response) } catch { return { accepted: false as const, code: "AUTONOMOUS_FINAL_SCHEMA" } }
      text = (response as unknown as { text: string }).text
      finalBasis = (response as unknown as import("@base-harness/domain-contracts").AutonomousFinalResponse).basedOn
    }
    if (finalBasis && canonicalJson(finalBasis) !== canonicalJson(this.runtime.autonomousBasis(this.input.sessionID, this.input.runId))) {
      return { accepted: false as const, code: "AUTONOMOUS_STALE_BASIS" }
    }
    if (text !== undefined) {
      const previous = this.textFinals.get(decisionId)
      if (previous && previous.text !== text) return { accepted: false as const, code: "AUTONOMOUS_REQUEST_CONFLICT" }
      if (previous) textReport = previous.report
      else {
        const stored = await this.store("report", text)
        textReport = stored.subject as SubjectRef & { kind: "report" }
        this.runtime.registerAutonomousSubject(this.input.sessionID, this.input.runId, textReport)
        this.textFinals.set(decisionId, { text, report: textReport })
      }
    }
    const normalized = this.module.normalizeDecision(frozen({
      response: frozen(structuredClone(response)),
      ...(textReport ? { textReport: frozen(structuredClone(textReport)) } : {}),
    }))
    let proposal: DecisionProposal
    try {
      if (normalized && typeof normalized === "object" && "schemaVersion" in normalized) {
        proposal = parseDecisionProposal(normalized)
        if (proposal.decisionId !== decisionId) return { accepted: false as const, code: "AUTONOMOUS_DECISION_BINDING" }
      } else {
        proposal = { schemaVersion: "decision-v1", decisionId, basis: finalBasis ?? this.runtime.autonomousBasis(this.input.sessionID, this.input.runId),
          observationIds: [], action: parseDecisionAction(normalized) }
      }
    } catch { return { accepted: false as const, code: "AUTONOMOUS_DECISION_SCHEMA" } }
    if (finalBasis && canonicalJson(proposal.basis) !== canonicalJson(finalBasis)) return { accepted: false as const, code: "AUTONOMOUS_FINAL_BINDING" }
    return this.runtime.submitAutonomousDecision(this.input.sessionID, this.input.runId, proposal)
  }

  async captureSource(bytes: Uint8Array, origin: string) {
    this.snapshot()
    this.assertInvocation("read", "read")
    const stored = await this.store("source", bytes, origin)
    this.runtime.registerAutonomousSubject(this.input.sessionID, this.input.runId, stored.subject)
    return structuredClone(stored)
  }

  proposeCheck(subject: SubjectRef, parameters: Json): CheckSpec {
    this.snapshot()
    if (!this.describeCheck) throw new Error("AUTONOMOUS_CHECK_REGISTRATION_UNSUPPORTED")
    const described = this.describeCheck(frozen(structuredClone(parameters)), this.subject(subject))
    const body = { ...described, schemaVersion: "check-spec-v1" as const, author: "model" as const }
    const check: CheckSpec = { ...body, ref: version("check:" + randomUUID(), 1, body) }
    assertAutonomousSchema("check", check)
    this.runtime.registerAutonomousCheck(this.input.sessionID, this.input.runId, check)
    this.checks.set(check.ref.id, frozen(structuredClone(check)))
    return structuredClone(check)
  }

  reserveModel(requestId: string, payload: Json, upperBound: AutonomousResourceUsage) {
    this.snapshot()
    if (this.input.executor.providerId) {
      const selected = payload && typeof payload === "object" && !Array.isArray(payload) ? payload : undefined
      if (selected?.providerId !== this.input.executor.providerId || selected?.modelId !== this.input.executor.modelId) {
        throw new Error("AUTONOMOUS_EXECUTOR_BINDING")
      }
    }
    return this.runtime.reserveAutonomousModel(this.input.sessionID, this.input.runId, requestId, payload, upperBound)
  }
  settleModel(requestId: string, usage: AutonomousResourceUsage) {
    return this.runtime.settleAutonomousModel(this.input.sessionID, this.input.runId, requestId, usage)
  }

  private subject(ref: SubjectRef): StoredAutonomousSubject {
    const stored = this.subjects.get(ref.id)
    if (!stored || !sameSubject(stored.subject, ref)) throw new Error("AUTONOMOUS_SUBJECT_UNKNOWN")
    return structuredClone(stored)
  }
  private check(ref: VersionRef): CheckSpec {
    const check = this.checks.get(ref.id)
    if (!check || canonicalJson(check.ref) !== canonicalJson(ref)) throw new Error("AUTONOMOUS_CHECK_UNKNOWN")
    return structuredClone(check)
  }

  private async store(kind: SubjectRef["kind"], value: string | Uint8Array, origin?: string): Promise<StoredAutonomousSubject> {
    const data = typeof value === "string" ? Buffer.from(value, "utf8") : Buffer.from(value)
    if (data.length > 10 * 1024 * 1024) throw new Error("AUTONOMOUS_ARTIFACT_LIMIT")
    const id = randomUUID()
    const file = id + ".data"
    await writeFile(join(this.snapshotRoot, file), data, { flag: "wx", mode: 0o600 })
    const manifestJson = canonicalJson({ kind, files: [{ path: file, sha256: digest(data), size: data.length }], dependencies: [] })
    const stored: StoredAutonomousSubject = { subject: { kind, id: kind + ":" + id, revision: 1, sha256: digest(manifestJson) }, manifestJson,
      ...(origin ? { origin } : {}) }
    this.subjects.set(stored.subject.id, frozen(stored))
    return structuredClone(stored)
  }
}
