import type { TuiCommand, TuiPlugin, TuiThemeCurrent } from "@base-harness/plugin/tui"
import { ANTIGRAVITY_ADAPTER_ID, ANTIGRAVITY_REASONING_OPTION } from "@base-harness/core/antigravity-protocol"
import type { BuiltinTuiPlugin } from "./builtins"
import { createEffect, createSignal, For, onCleanup, Show, untrack } from "solid-js"
import { createHarnessStatusBinding, harnessRootSession } from "../harness/session-status"
import type { ScrollBoxRenderable } from "@opentui/core"
import { useTerminalDimensions } from "@opentui/solid"
import { useBindings } from "../keymap"
import { harnessPanelLayout, harnessPlanningCue } from "../harness/panel-presentation"
import { HarnessPanelFrame } from "../harness/panel-frame"
import { unwrapHarnessResponse } from "../harness/control-response"
import {
  pendingHarnessSelection,
  queueHarnessControl,
  subscribePendingHarnessControls,
  type HarnessControl,
} from "../harness/pending-control"
import { discoverAntigravityCli } from "../harness/antigravity-cli"
import { harnessDisplayPhase, harnessLifecycleLabel } from "../harness/status-presentation"

type WorkerStatus = {
  workUnitId: string
  title: string
  state: string
  scopeId?: string
  repairCount: number
  failureFingerprint?: string
}

type HarnessStatus = {
  sessionID: string
  runId: string
  history?: {
    runId: string
    recordedAt: string
    recordedPhase: string
    phase: string
    readOnly: true
    revalidated: false
    goal: string
    goalTruncated: boolean
    workers: WorkerStatus[]
    evidenceCount: number
    candidateCount: number
    evidenceRefs: string[]
    candidateRefs: string[]
    referencesTruncated: boolean
    repairCount: number
    assuranceLevel?: "fast" | "adaptive" | "strict"
  }
  execution?: {
    adapterID: string
    modelID?: string
    options?: Record<string, string>
    capabilityRevision?: string
  }
  goal: string
  phase: string
  workers: WorkerStatus[]
  activeCount: number
  queuedCount: number
  outcome?: string
  verificationState: string
  configuredProfile?: "fast" | "adaptive" | "strict"
  effectiveProfile?: "fast" | "adaptive" | "strict"
  assuranceLevel?: "fast" | "adaptive" | "strict"
  failureKind?: string | null
  failedCriterion?: string | null
  missingEvidence: string[]
  repairCount: number
  maxSameFailureRepairs: number
  evidenceCount: number
  candidateCount: number
  evidenceRefs: string[]
  candidateRefs: string[]
  readyEligible: boolean
  message?: string
  domain?: "develop" | "general"
  skills?: Array<"hackathon">
  planningPreference?: "auto" | "plan_once"
  planOnly?: boolean
  planningState?: string
  planningDecision?: "direct" | "planned"
  activePlanId?: string
  activePlanRevision?: number
  planRecovery?: { code: string; action: "planning.discard"; planId: string; revision: number }
  goalContract?: {
    revision: number
    hash?: string
    claims: Array<{ id: string; statement: string; required: boolean; criterionIds: string[] }>
    criteria: Array<{ id: string; statement: string; required: boolean; risk?: string; claimIds: string[] }>
  }
  plan?: {
    id: string
    revision: number
    assumptions: string[]
    steps: Array<{
      id: string
      title: string
      priority: string
      claimIds: string[]
      criterionIds: string[]
      dependsOn: string[]
      readSet: string[]
      writeSet: string[]
    }>
  }
  preflight?: {
    decision: "accept" | "meta_review_required" | "needs_input"
    reasons: string[]
    questionCount: number
    assumptionCount: number
    reviewerCallCount: number
    requiredDecisions?: Array<{
      id: string
      statement: string
      impact: string
      affectedClaimIds: string[]
      affectedCriterionIds: string[]
    }>
    assumptions?: string[]
  }
  metaReview?: {
    phase: "goal_contract" | "plan"
    outcome: "pass" | "revise" | "needs_input"
    issueCount: number
    blockingIssueCount: number
    issues?: Array<{
      id: string
      severity: "blocking" | "warning"
      statement: string
      targetIds?: string[]
    }>
  }
  metrics?: {
    observedActions: number
    workers: number
    activeWorkers: number
    repairs: number
    evidence: number
    sandboxRuns: number
  }
  isolation?: {
    backend: string
    containment: string
    network: string
    state: string
    code?: string
  }
}

const initialStatus = (maxSameFailureRepairs = 2): HarnessStatus => ({
  sessionID: "",
  runId: "",
  goal: "",
  phase: "inactive",
  workers: [],
  activeCount: 0,
  queuedCount: 0,
  verificationState: "inactive",
  missingEvidence: [],
  repairCount: 0,
  maxSameFailureRepairs,
  evidenceCount: 0,
  candidateCount: 0,
  evidenceRefs: [],
  candidateRefs: [],
  readyEligible: false,
})

const record = (value: unknown): Record<string, unknown> | undefined =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined

const text = (value: unknown): string | undefined => (typeof value === "string" ? value : undefined)

const outcomeColor = (status: HarnessStatus): string => {
  if (status.outcome === "ready" || status.phase === "ready") return "#78c091"
  if (status.phase === "repair" || status.outcome === "repair" || status.outcome === "repair_exhausted") return "#e6b566"
  if (status.phase === "blocked" || status.phase === "interrupted" || status.outcome === "failure") return "#e06c75"
  return "#7aa2c8"
}

const clip = (value: string, length = 72) =>
  value.length > length ? value.slice(0, Math.max(0, length - 1)) + "..." : value

function VerificationPanel(props: {
  status: HarnessStatus
  background: TuiThemeCurrent["backgroundPanel"]
  overlay?: boolean
  view?: "summary" | "goal" | "evidence"
}) {
  const expandedGoal = () => props.view === "goal"
  const expandedEvidence = () => props.view === "evidence"
  const dimensions = useTerminalDimensions()
  const layout = () => harnessPanelLayout(dimensions().width, dimensions().height)
  let scroll: ScrollBoxRenderable | undefined
  const scrollPage = (direction: -1 | 1) => {
    if (!scroll) return false
    scroll.scrollBy(direction * Math.max(1, layout().bodyHeight - 1))
    return true
  }
  useBindings(() => ({
    enabled: () => Boolean(props.overlay),
    bindings: [
      { key: "pageup", desc: "Scroll harness details up", cmd: () => scrollPage(-1) },
      { key: "pagedown", desc: "Scroll harness details down", cmd: () => scrollPage(1) },
    ],
  }))
  createEffect(() => {
    props.view
    props.status.runId
    untrack(() => { if (scroll) scroll.scrollBy(-scroll.scrollTop) })
  })
  const title = () => {
    const phase = harnessDisplayPhase(props.status)
    if (phase.startsWith("history_")) {
      const value = "HISTORY " + props.status.history!.phase.toUpperCase()
      return props.overlay ? clip(value, layout().contentWidth) : value
    }
    const assurance = phase === "ready"
      ? " (" + (props.status.assuranceLevel ?? props.status.effectiveProfile ?? "adaptive") + ")"
      : ""
    const value = (layout().contentWidth >= 36 ? "VERIFIED STATE " : "") + phase.toUpperCase() + assurance
    return props.overlay ? clip(value, layout().contentWidth) : value
  }
  const body = () => (
    <box flexDirection="column" flexShrink={0}>
      <Show when={props.status.history}>
        {(history) => (
          <box flexDirection="column">
            <text fg="#e6b566">Past run only. Not reverified against the current workspace.</text>
            <text fg="#a8b3c7">Current domain {props.status.domain ?? "develop"}{props.status.skills?.includes("hackathon") ? " + hackathon" : ""}</text>
            <text fg="#a8b3c7">{harnessLifecycleLabel(props.status)}</text>
            <text fg="#778399">{history().runId} / {history().recordedAt}</text>
            <text fg="#a8b3c7">Previous goal</text>
            <text>{history().goal}</text>
            <Show when={history().goalTruncated}><text fg="#778399">Goal summary truncated.</text></Show>
            <Show when={history().recordedPhase !== history().phase}>
              <text fg="#e6b566">Last recorded phase: {history().recordedPhase}. Execution was not resumed.</text>
            </Show>
            <text fg="#a8b3c7">Past workers {history().workers.length} / Evidence {history().evidenceCount} / Candidates {history().candidateCount} / Repairs {history().repairCount}</text>
            <Show when={history().assuranceLevel}><text fg="#778399">Past assurance: {history().assuranceLevel}</text></Show>
            <For each={history().workers}>
              {(worker) => <text fg="#778399">- {worker.workUnitId} [{worker.state}] {clip(worker.title, 44)}</text>}
            </For>
            <Show when={expandedEvidence()}>
              <For each={history().evidenceRefs}>{(reference) => <text fg="#778399">Past evidence: {clip(reference)}</text>}</For>
              <For each={history().candidateRefs}>{(reference) => <text fg="#778399">Past candidate: {clip(reference)}</text>}</For>
              <Show when={history().referencesTruncated}><text fg="#778399">Reference list truncated.</text></Show>
            </Show>
          </box>
        )}
      </Show>
      <Show when={!props.status.history}>
      <Show when={harnessPlanningCue(props.status, false)}>
        {(cue) => <text fg="#e6b566">{cue().message}</text>}
      </Show>
      <text fg="#a8b3c7">Goal</text>
      <text>{props.status.goal || "Waiting for the Host Coordinator"}</text>
      <text fg="#a8b3c7">
        Domain {props.status.domain ?? "develop"}
        {props.status.skills?.includes("hackathon") ? " + hackathon" : ""}
      </text>
      <Show when={props.status.execution}>
        {(execution) => (
          <text fg="#a8b3c7">
            Execution {execution().adapterID}
            {execution().modelID ? ` / ${execution().modelID}` : " / provider default"}
            {execution().options?.[ANTIGRAVITY_REASONING_OPTION]
              ? ` / ${execution().options?.[ANTIGRAVITY_REASONING_OPTION]}`
              : ""}
          </text>
        )}
      </Show>
      <text fg="#a8b3c7">
{harnessLifecycleLabel(props.status)}
        {props.status.activePlanId
          ? " / " + props.status.activePlanId + "@" + String(props.status.activePlanRevision)
          : ""}
      </text>
      <Show when={props.status.preflight}>
        {(preflight) => (
          <box flexDirection="column">
            <text fg="#a8b3c7">
              Preflight {preflight().decision} / questions {String(preflight().questionCount)} / assumptions {String(preflight().assumptionCount)} / reviews {String(preflight().reviewerCallCount)}
            </text>
            <For each={preflight().requiredDecisions ?? []}>
              {(decision) => <text fg="#e6b566">? {decision.id} [{decision.impact}] {clip(decision.statement)}</text>}
            </For>
            <For each={preflight().assumptions ?? []}>
              {(assumption) => <text fg="#778399">~ {clip(assumption)}</text>}
            </For>
          </box>
        )}
      </Show>
      <text fg="#a8b3c7">
        Workers {String(props.status.activeCount)} active / {String(props.status.queuedCount)} queued / {String(props.status.workers.length)} total
      </text>
      <For each={props.status.workers}>
        {(worker) => (
          <text fg={worker.state === "failed" || worker.state === "repair_exhausted" ? "#e06c75" : "#778399"}>
            {worker.state === "running" ? ">" : "-"} {worker.workUnitId} [{worker.state}] r{String(worker.repairCount)} {clip(worker.title, 44)}
          </text>
        )}
      </For>
      <Show when={props.status.goalContract}>
        {(contract) => (
          <box flexDirection="column">
            <text fg="#a8b3c7">GoalContract r{String(contract().revision)} / {contract().claims.length} claims / {contract().criteria.length} criteria</text>
            <For each={expandedGoal() ? contract().claims : contract().claims.slice(0, 3)}>
              {(claim) => <text>{claim.required ? "*" : "-"} {claim.id}: {clip(claim.statement)}</text>}
            </For>
            <Show when={expandedGoal()}>
              <For each={contract().criteria}>
                {(criterion) => <text fg="#778399">- {criterion.id} [{criterion.risk ?? "unknown"}]: {clip(criterion.statement)}</text>}
              </For>
            </Show>
          </box>
        )}
      </Show>
      <Show when={props.status.plan}>
        {(plan) => (
          <box flexDirection="column">
            <text fg="#a8b3c7">Plan {plan().id}@{String(plan().revision)} / {String(plan().steps.length)} steps</text>
            <For each={plan().steps.slice(0, 6)}>
              {(step) => <text>- {step.id} [{step.priority}] {clip(step.title, 48)}</text>}
            </For>
          </box>
        )}
      </Show>
      <text fg="#a8b3c7">
        Evidence {String(props.status.evidenceCount)} / Candidates {String(props.status.candidateCount)}
      </text>
      <Show when={expandedEvidence()}>
        <box flexDirection="column">
          <For each={props.status.evidenceRefs}>
            {(reference) => <text fg="#78c091">+ {clip(reference)}</text>}
          </For>
          <For each={props.status.candidateRefs}>
            {(reference) => <text fg="#e6b566">? {clip(reference)}</text>}
          </For>
        </box>
      </Show>
      <Show when={props.status.failedCriterion}>
        <text fg="#e6b566">Criterion {props.status.failedCriterion}</text>
      </Show>
      <Show when={props.status.failureKind}>
        <text fg="#e06c75">FailureKind {props.status.failureKind}</text>
      </Show>
      <Show when={props.status.missingEvidence.length > 0}>
        <text>{props.status.missingEvidence.join(" | ")}</text>
      </Show>
      <text fg="#a8b3c7">
        Repairs {String(props.status.repairCount)} / {String(props.status.maxSameFailureRepairs)}
      </text>
      <Show when={props.status.isolation}>
        {(isolation) => <text fg="#778399">Isolation {isolation().backend} / {isolation().containment} / {isolation().network} / {isolation().state}</text>}
      </Show>
      </Show>
    </box>
  )
  return (
    <HarnessPanelFrame
      overlay={props.overlay}
      layout={layout()}
      title={title()}
      tone={outcomeColor(props.status)}
      background={props.background}
      onScrollBox={(value) => { scroll = value }}
    >
      {body()}
    </HarnessPanelFrame>
  )
}

type SessionHarnessClient = {
  harness(input: { sessionID: string; directory?: string }): Promise<unknown>
  harnessVerify(input: { sessionID: string; directory?: string; reason: "automatic" | "manual" | "completion" }): Promise<unknown>
  harnessCancel(input: { sessionID: string; directory?: string }): Promise<unknown>
  harnessControl(input: { sessionID: string; directory?: string; body: HarnessControl }): Promise<unknown>
}

const tui: TuiPlugin = async (api) => {
  const [status, setStatus] = createSignal(initialStatus(2))
  const [overlay, setOverlay] = createSignal(false)
  const [overlayView, setOverlayView] = createSignal<"summary" | "goal" | "evidence">("summary")
  const [pendingSelection, setPendingSelection] = createSignal(pendingHarnessSelection())

  void api.client.config
    .get()
    .then((response) => {
      const config = record(response.data)
      const verification = record(config?.verification)
      const repairs = verification?.maxSameFailureRepairs
      if (typeof repairs === "number" && Number.isInteger(repairs) && repairs >= 0) {
        setStatus((current) => ({ ...current, maxSameFailureRepairs: repairs }))
      }
    })
    .catch(() => {})

  let verificationPending = false
  const stopPendingSubscription = subscribePendingHarnessControls(() => {
    const next = pendingHarnessSelection()
    setPendingSelection(next)
    if (!rootScopeId()) {
      setStatus((current) => ({
        ...current,
        domain: next.domain,
        skills: next.hackathon ? ["hackathon"] : [],
        planningPreference: next.planOnce ? "plan_once" : "auto",
      }))
    }
  })
  onCleanup(stopPendingSubscription)

  const client = api.client.session as unknown as SessionHarnessClient
  const unwrap = (value: unknown): HarnessStatus => unwrapHarnessResponse<HarnessStatus>(value)
  const rootScopeId = () => {
    const route = api.route.current
    if (route.name !== "session") return ""
    return harnessRootSession(text(record(route.params)?.sessionID), (id) => api.state.session.get(id)) ?? ""
  }
  const binding = createHarnessStatusBinding<HarnessStatus>({
    fetch: async (target) => unwrap(await client.harness(target)),
    publish: (next) => { setStatus(next) },
    reset: () => {
      const selection = pendingHarnessSelection()
      setStatus((current) => ({
        ...initialStatus(current.maxSameFailureRepairs),
        domain: selection.domain,
        skills: selection.hackathon ? ["hackathon"] : [],
        planningPreference: selection.planOnce ? "plan_once" : "auto",
      }))
    },
  })
  onCleanup(() => binding.dispose())
  const currentTarget = () => {
    const sessionID = rootScopeId()
    binding.select(sessionID ? { sessionID, directory: api.state.path.directory } : undefined)
    return binding.current()
  }
  const refresh = () => {
    currentTarget()
    return binding.refresh()
  }
  const notify = (title: string, message: string, variant: "info" | "success" | "warning" | "error" = "info") =>
    api.ui.toast({ title, message, variant })
  const verify = async (reason: "automatic" | "manual") => {
    const target = currentTarget()
    if (!target || verificationPending) return
    if (
      status().planningState === "plan_ready" ||
      status().planningState === "awaiting_input" ||
      status().planningState === "contract_building" ||
      status().planningState === "contract_preflight" ||
      status().planningState === "contract_reviewing" ||
      status().planningState === "plan_building" ||
      status().planningState === "plan_reviewing"
    ) {
      return
    }
    verificationPending = true
    try {
      const next = unwrap(
        await client.harnessVerify({
          ...target,
          reason,
        }),
      )
      if (!binding.accept(next, target)) return
      if (next.outcome === "ready") {
        notify(
          `Ready (${next.assuranceLevel ?? next.effectiveProfile ?? "adaptive"})`,
          "Independent Host verification passed.",
          "success",
        )
      } else if (next.outcome === "repair" || next.outcome === "repair_exhausted") {
        notify("Verification repair", next.message ?? "The owning worker is being repaired locally.", "warning")
      } else if (next.phase === "blocked" || next.outcome === "failure") {
        notify("Verification blocked", next.message ?? "Ready was not issued.", "error")
      }
    } catch (error) {
      notify("Coordinator unavailable", error instanceof Error ? error.message : String(error), "error")
    } finally {
      verificationPending = false
    }
  }

  const control = async (body: HarnessControl) => {
    const target = currentTarget()
    if (!target) {
      if (body.type === "planning.execute") {
        notify("No reviewed plan", "Create a session and build a plan before execution.", "warning")
        return
      }
      queueHarnessControl(body)
      notify("Harness control staged", "The setting will be applied before the first request.", "success")
      return
    }
    try {
      const next = unwrap(await client.harnessControl({ ...target, body }))
      if (binding.accept(next, target) && body.type === "planning.plan_once") {
        notify("Plan-only enabled", "The next request will stop at a reviewed plan. Use /execute to run it.", "success")
      }
    } catch (error) {
      notify("Kernel control rejected", error instanceof Error ? error.message : String(error), "error")
    }
  }

  const selectAntigravity = async () => {
    let capabilities: Awaited<ReturnType<typeof discoverAntigravityCli>>
    try {
      capabilities = await discoverAntigravityCli({
        client: api.client,
        sessionID: rootScopeId() || undefined,
        directory: api.state.path.directory,
      })
    } catch (error) {
      notify("Antigravity unavailable", error instanceof Error ? error.message : String(error), "error")
      return
    }

    const DialogSelect = api.ui.DialogSelect as any
    const selectEffort = (modelID?: string) => {
      api.ui.dialog.replace(() => (
        <DialogSelect
          title="Antigravity reasoning effort"
          options={[
            { title: "Provider default", value: "" },
            ...capabilities.reasoningEfforts.map((value) => ({ title: value, value })),
          ]}
          onSelect={(option: { value: string }) => {
            api.ui.dialog.clear()
            void control({
              type: "execution.select",
              selection: {
                adapterID: ANTIGRAVITY_ADAPTER_ID,
                modelID,
                options: option.value ? { [ANTIGRAVITY_REASONING_OPTION]: option.value } : undefined,
                capabilityRevision: capabilities.revision,
              },
            })
          }}
        />
      ))
    }

    api.ui.dialog.replace(() => (
      <DialogSelect
        title="Antigravity execution"
        options={[
          { title: "Provider default model", value: "" },
          ...capabilities.models.map((value) => ({ title: value, value })),
        ]}
        onSelect={(option: { value: string }) => selectEffort(option.value || undefined)}
      />
    ))
  }

  const refreshWithNotice = () => refresh().catch((error) => {
    notify("Coordinator unavailable", error instanceof Error ? error.message : String(error), "error")
  })
  createEffect(() => {
    const sessionID = rootScopeId()
    const directory = api.state.path.directory
    untrack(() => {
      if (binding.select(sessionID ? { sessionID, directory } : undefined)) void refreshWithNotice()
    })
  })

  type HarnessCommand = TuiCommand & {
    argument?: string
    onArguments?: (values: readonly string[]) => void | Promise<void>
  }
  const harnessCommands: HarnessCommand[] = [
    {
      value: "harness.domain.develop",
      title: "Develop domain",
      description: "Enable workspace development",
      slash: { name: "develop" },
      category: "Harness",
      onSelect: () => void control({ type: "domain.set", domain: "develop" }),
    },
    {
      value: "harness.domain.general",
      title: "General domain",
      description: "Use read-only general lookup mode",
      slash: { name: "general" },
      category: "Harness",
      onSelect: () => void control({ type: "domain.set", domain: "general" }),
    },
    {
      value: "harness.skill.hackathon",
      title: "Hackathon skill",
      description: "Enable demo-first develop planning",
      slash: { name: "hackathon" },
      category: "Harness",
      onSelect: () => void control({ type: "skill.set", skill: "hackathon", enabled: true }),
    },
    {
      value: "harness.skill.hackathon.off",
      title: "Disable hackathon skill",
      description: "Keep the current domain and disable demo-first planning",
      slash: { name: "hackathon off" },
      category: "Harness",
      onSelect: () => void control({ type: "skill.set", skill: "hackathon", enabled: false }),
    },
    {
      value: "harness.execution.antigravity",
      title: "Antigravity execution",
      description: "Select an official agy model and reasoning effort",
      slash: { name: "antigravity" },
      category: "Harness",
      onSelect: () => void selectAntigravity(),
    },
    {
      value: "harness.execution.antigravity.off",
      title: "Disable Antigravity execution",
      description: "Return implementation workers to the selected native provider",
      slash: { name: "antigravity off" },
      category: "Harness",
      onSelect: () => void control({ type: "execution.select" }),
    },
    {
      value: "harness.plan.once",
      title: "Plan next request",
      description: "Build and review one plan without executing it",
      slash: { name: "plan" },
      category: "Harness",
      onSelect: () => void control({ type: "planning.plan_once" }),
    },
    {
      value: "harness.plan.discard",
      title: "Discard active plan",
      description: "Discard the current unexecuted plan",
      slash: { name: "plan discard" },
      category: "Harness",
      onSelect: () => void control({ type: "planning.discard" }),
    },
    {
      value: "harness.plan.execute",
      title: "Execute active plan",
      description: "Execute the reviewed plan revision",
      slash: { name: "execute" },
      argument: "planId",
      category: "Harness",
      onArguments: ([planId]) => void control({ type: "planning.execute", planId }),
      onSelect: () => void control({ type: "planning.execute" }),
    },
    {
      value: "harness.toggle",
      title: "Harness status",
      description: "Toggle the Host Coordinator overlay",
      slash: { name: "harness" },
      category: "Harness",
      onSelect: () => {
        setOverlayView("summary")
        setOverlay((value) => !value)
        void refreshWithNotice()
      },
    },
    {
      value: "harness.goal",
      title: "GoalContract",
      description: "Show the active root goal",
      slash: { name: "goal" },
      category: "Harness",
      onSelect: () => {
        setOverlayView("goal")
        setOverlay(true)
        void refreshWithNotice()
      },
    },
    {
      value: "harness.verify",
      title: "Verify now",
      description: "Request Host Coordinator verification",
      slash: { name: "verify" },
      category: "Harness",
      onSelect: () => void verify("manual"),
    },
    {
      value: "harness.evidence",
      title: "Evidence",
      description: "Show trusted evidence and candidate counts",
      slash: { name: "evidence" },
      category: "Harness",
      onSelect: () => {
        setOverlayView("evidence")
        setOverlay(true)
        void refreshWithNotice()
      },
    },
  ]

  api.keymap.registerLayer({
    commands: harnessCommands.map((command) => ({
      name: command.value,
      title: command.title,
      desc: command.description,
      category: command.category,
      namespace: "palette",
      slashName: command.slash?.name,
      slashAliases: command.slash?.aliases,
      slashArgument: command.argument,
      run(context) {
        if (command.onArguments) {
          const raw = record(context.payload)?.arguments
          const args = Array.isArray(raw) ? raw : []
          if ((raw !== undefined && !Array.isArray(raw)) || args.length > 1 || args.some((value) => typeof value !== "string")) {
            notify("Invalid control command", "Use /execute [planId].", "error")
            return
          }
          return command.onArguments(args)
        }
        return command.onSelect?.(api.ui.dialog)
      },
    })),
  })

  api.slots.register({
    order: 50,
    slots: {
      sidebar_content: () => <VerificationPanel status={status()} background={api.theme.current.backgroundPanel} view="summary" />,
      app_bottom: () => (
        <box paddingLeft={1} paddingRight={1}>
          <text fg="#7aa2c8">
            HARNESS {status().domain ?? pendingSelection().domain}
            {(status().skills?.includes("hackathon") ?? pendingSelection().hackathon) ? " + hackathon" : ""}
            {(status().execution ?? pendingSelection().execution)?.adapterID
              ? ` / ${(status().execution ?? pendingSelection().execution)?.adapterID}`
              : ""}
            {harnessPlanningCue(status(), pendingSelection().planOnce)
              ? ` / ${harnessPlanningCue(status(), pendingSelection().planOnce)!.label}` : ""}
            {pendingSelection().count > 0 ? ` / ${String(pendingSelection().count)} staged` : ""}
            {harnessDisplayPhase(status()) !== "inactive" ? ` / ${harnessDisplayPhase(status())}` : ""}
          </text>
        </box>
      ),
      app: () => (
        <Show when={overlay()}>
          <box position="absolute" top={1} right={2} zIndex={100}>
            <VerificationPanel status={status()} background={api.theme.current.backgroundPanel} overlay view={overlayView()} />
          </box>
        </Show>
      ),
    },
  })

  const events = api.event as unknown as {
    on(type: string, handler: (event: { properties?: unknown }) => void): void
  }
  events.on("harness.status", (event) => {
    const properties = record(event.properties)
    const next = record(properties?.status) as unknown as HarnessStatus | undefined
    if (!next || !rootScopeId() || next.sessionID !== rootScopeId()) return
    binding.accept(next, currentTarget())
  })
  events.on("session.status", (event) => {
    const properties = record(event.properties)
    const eventSessionId = text(properties?.sessionID)
    const state = record(properties?.status)
    if (!eventSessionId) return
    if (eventSessionId === rootScopeId() && state?.type === "idle") {
      void refresh().catch(() => undefined)
    }
  })
}

export const VerificationPlugin: BuiltinTuiPlugin = {
  id: "internal:base-harness-verification",
  tui,
}
