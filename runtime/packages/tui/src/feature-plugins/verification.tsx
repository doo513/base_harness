import type { TuiCommand, TuiPlugin } from "@base-harness/plugin/tui"
import type { BuiltinTuiPlugin } from "./builtins"
import { createSignal, Show } from "solid-js"
import { useSync } from "../context/sync"

type WorkerStatus = {
  workUnitId: string
  title: string
  state: string
  scopeId?: string
  repairCount: number
}

type HarnessStatus = {
  sessionID: string
  runId: string
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
  readyEligible: boolean
  message?: string
  domain?: "develop" | "general"
  skills?: Array<"hackathon">
  planningPreference?: "auto" | "plan_once"
  planningState?: string
  planningDecision?: "direct" | "planned"
  activePlanId?: string
  activePlanRevision?: number
  preflight?: {
    decision: "accept" | "meta_review_required" | "needs_input"
    reasons: string[]
    questionCount: number
    assumptionCount: number
    reviewerCallCount: number
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
    }>
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

function VerificationPanel(props: { status: HarnessStatus; overlay?: boolean }) {
  return (
    <box
      flexDirection="column"
      border={props.overlay}
      borderStyle="rounded"
      borderColor={outcomeColor(props.status)}
      paddingLeft={1}
      paddingRight={1}
      paddingTop={props.overlay ? 1 : 0}
      paddingBottom={props.overlay ? 1 : 0}
      width={props.overlay ? Math.min(process.stdout.columns ?? 80, 64) : undefined}
    >
      <text fg={outcomeColor(props.status)}>
        <b>VERIFIED STATE</b> {props.status.phase.toUpperCase()}
        {props.status.phase === "ready"
          ? ` (${props.status.assuranceLevel ?? props.status.effectiveProfile ?? "adaptive"})`
          : ""}
      </text>
      <text fg="#a8b3c7">Goal</text>
      <text>{props.status.goal || "Waiting for the Host Coordinator"}</text>
      <text fg="#a8b3c7">
        Domain {props.status.domain ?? "develop"}
        {props.status.skills?.includes("hackathon") ? " + hackathon" : ""}
      </text>
      <text fg="#a8b3c7">
        Planning {props.status.planningState ?? "idle"}
        {props.status.activePlanId
          ? " / " + props.status.activePlanId + "@" + String(props.status.activePlanRevision)
          : ""}
      </text>
      <Show when={props.status.preflight}>
        {(preflight) => (
          <text fg="#a8b3c7">
            Preflight {preflight().decision} / questions {String(preflight().questionCount)} / assumptions {String(preflight().assumptionCount)} / reviews {String(preflight().reviewerCallCount)}
          </text>
        )}
      </Show>
      <text fg="#a8b3c7">
        Workers {String(props.status.activeCount)} active / {String(props.status.queuedCount)} queued / {String(props.status.workers.length)} total
      </text>
      <text fg="#a8b3c7">
        Evidence {String(props.status.evidenceCount)} / Candidates {String(props.status.candidateCount)}
      </text>
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
      <Show when={props.overlay}>
        <text fg="#778399">Run /harness again to close</text>
      </Show>
    </box>
  )
}

type SessionHarnessClient = {
  harness(input: { sessionID: string; directory?: string }): Promise<unknown>
  harnessVerify(input: { sessionID: string; directory?: string; reason: "automatic" | "manual" | "completion" }): Promise<unknown>
  harnessCancel(input: { sessionID: string; directory?: string }): Promise<unknown>
  harnessControl(input: {
    sessionID: string
    directory?: string
  } & (
    | { type: "domain.set"; domain: "develop" | "general" }
    | { type: "skill.set"; skill: "hackathon"; enabled: boolean }
    | { type: "planning.plan_once" }
    | { type: "planning.discard" }
    | { type: "planning.execute"; planId?: string }
  )): Promise<unknown>
}

const tui: TuiPlugin = async (api) => {
  const sync = useSync()
  const maxRepairs = () => sync.data.config.verification?.maxSameFailureRepairs ?? 2
  const automatic = () => sync.data.config.verification?.trigger !== "manual"
  const [status, setStatus] = createSignal(initialStatus(maxRepairs()))
  const [overlay, setOverlay] = createSignal(false)
  let activeRootScopeId = ""
  let fetchedRootScopeId = ""
  let verificationPending = false

  const client = api.client.session as unknown as SessionHarnessClient
  const unwrap = (value: unknown): HarnessStatus => {
    const outer = record(value)
    if (outer?.error) throw new Error(text(record(outer.error)?.message) ?? "Harness API request failed")
    return (outer?.data ?? value) as HarnessStatus
  }
  const selectRootScope = (sessionId: string) => {
    let root = sessionId
    let current = api.state.session.get(root)
    while (current?.parentID) {
      root = current.parentID
      current = api.state.session.get(root)
    }
    activeRootScopeId = root
  }
  const rootScopeId = () => activeRootScopeId || status().sessionID
  const refresh = async () => {
    if (!rootScopeId()) return
    const next = unwrap(
      await client.harness({
        sessionID: rootScopeId(),
        directory: api.state.path.directory,
      }),
    )
    setStatus(next)
    return next
  }
  const notify = (title: string, message: string, variant: "info" | "success" | "warning" | "error" = "info") =>
    api.ui.toast({ title, message, variant })
  const verify = async (reason: "automatic" | "manual") => {
    if (!rootScopeId() || verificationPending) return
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
          sessionID: rootScopeId(),
          directory: api.state.path.directory,
          reason,
        }),
      )
      setStatus(next)
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

  const control = async (
    body:
      | { type: "domain.set"; domain: "develop" | "general" }
      | { type: "skill.set"; skill: "hackathon"; enabled: boolean }
      | { type: "planning.plan_once" }
      | { type: "planning.discard" }
      | { type: "planning.execute"; planId?: string },
  ) => {
    if (!rootScopeId()) return
    try {
      setStatus(
        unwrap(
          await client.harnessControl({
            sessionID: rootScopeId(),
            directory: api.state.path.directory,
            ...body,
          }),
        ),
      )
    } catch (error) {
      notify("Kernel control rejected", error instanceof Error ? error.message : String(error), "error")
    }
  }

  api.command?.register((): TuiCommand[] => [
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
      category: "Harness",
      onSelect: () => void control({ type: "planning.execute" }),
    },
    {
      value: "harness.toggle",
      title: "Harness status",
      description: "Toggle the Host Coordinator overlay",
      slash: { name: "harness" },
      category: "Harness",
      onSelect: () => {
        setOverlay((value) => !value)
        void refresh()
      },
    },
    {
      value: "harness.goal",
      title: "GoalContract",
      description: "Show the active root goal",
      slash: { name: "goal" },
      category: "Harness",
      onSelect: () => notify("GoalContract", status().goal || "No active Host run"),
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
      onSelect: () => notify("Evidence", `${status().evidenceCount} trusted / ${status().candidateCount} candidates`),
    },
  ])

  api.slots.register({
    order: 50,
    slots: {
      sidebar_content: (_context, props) => {
        selectRootScope(props.session_id)
        if (fetchedRootScopeId !== rootScopeId()) {
          fetchedRootScopeId = rootScopeId()
          void refresh()
        }
        return <VerificationPanel status={status()} />
      },
      app: () => (
        <Show when={overlay()}>
          <box position="absolute" top={2} right={2} zIndex={100}>
            <VerificationPanel status={status()} overlay />
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
    if (!next || (rootScopeId() && next.sessionID !== rootScopeId())) return
    setStatus(next)
  })
  events.on("session.status", (event) => {
    const properties = record(event.properties)
    const eventSessionId = text(properties?.sessionID)
    const state = record(properties?.status)
    if (!eventSessionId) return
    selectRootScope(eventSessionId)
    if (eventSessionId === rootScopeId() && state?.type === "idle" && automatic()) {
      void (async () => {
        const next = await refresh()
        if (next?.planningState === "plan_ready" || next?.planningState === "awaiting_input") return
        await verify("automatic")
      })()
    }
  })
}

export const VerificationPlugin: BuiltinTuiPlugin = {
  id: "internal:base-harness-verification",
  tui,
}
