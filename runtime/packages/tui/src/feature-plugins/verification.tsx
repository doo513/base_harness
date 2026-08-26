import {
  classifyRuntimeFailure,
  goalSource,
  materializeProposal,
  createVerificationClient,
  type GoalContractProposal,
  type ProcessVerificationClient,
  type VerificationStatus,
} from "@base-harness/verification"
import type { TuiCommand, TuiPlugin } from "@base-harness/plugin/tui"
import type { BuiltinTuiPlugin } from "./builtins"
import { createSignal, Show } from "solid-js"

const initialStatus = (): VerificationStatus => ({
  state: "inactive",
  goal: "",
  runId: "",
  scopeId: "",
  rootScopeId: "",
  evidenceRefs: [],
  candidateRefs: [],
  criterionResults: [],
  claimResults: [],
  evidenceFamilies: [],
  readyRef: null,
  maxSameFailureRepairs: 2,
})

const record = (value: unknown): Record<string, unknown> | undefined =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined

const text = (value: unknown): string | undefined =>
  typeof value === "string" ? value : undefined

const toolState = (
  event: unknown,
): {
  sessionId: string
  callId: string
  tool: string
  status: string
  input?: unknown
  output?: unknown
  error?: unknown
} | undefined => {
  const value = record(event)
  if (value?.type !== "message.part.updated") return
  const properties = record(value.properties)
  const part = record(properties?.part)
  if (part?.type !== "tool") return
  const state = record(part.state)
  const status = text(state?.status)
  const callId = text(part.callID) ?? text(part.id)
  const sessionId = text(part.sessionID) ?? text(properties?.sessionID)
  const tool = text(part.tool)
  if (!status || !callId || !sessionId || !tool) return
  return {
    sessionId,
    callId,
    tool,
    status,
    input: state?.input,
    output: state?.output,
    error: state?.error,
  }
}

const outcomeColor = (status: VerificationStatus): string => {
  if (status.state === "ready") return "#78c091"
  if (status.state === "repair") return "#e6b566"
  if (status.state === "blocked" || status.state === "failure") return "#e06c75"
  return "#7aa2c8"
}

function VerificationPanel(props: { status: VerificationStatus; overlay?: boolean }) {
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
        <b>VERIFIED STATE</b> {props.status.state.toUpperCase()}
      </text>
      <text fg="#a8b3c7">Goal</text>
      <text>{props.status.goal || "Waiting for the first session goal"}</text>
      <text fg="#a8b3c7">
        Evidence {String(props.status.evidenceRefs.length)} / Candidates{" "}
        {String(props.status.candidateRefs.length)}
      </text>
      <text fg="#a8b3c7">
        Criteria {String(props.status.criterionResults.filter((item) => item.result === "verified").length)}
        /{String(props.status.criterionResults.length)} · Families {String(props.status.evidenceFamilies.length)}
      </text>
      <Show when={props.status.failedCriterion}>
        <text fg="#e6b566">Criterion {props.status.failedCriterion}</text>
      </Show>
      <Show when={props.status.failureKind}>
        <text fg="#e06c75">FailureKind {props.status.failureKind}</text>
      </Show>
      <Show when={(props.status.missingEvidence?.length ?? 0) > 0}>
        <text>{props.status.missingEvidence?.join(" | ")}</text>
      </Show>
      <text fg="#a8b3c7">
        Repairs {String(props.status.repairCount ?? 0)} /{" "}
        {String(props.status.maxSameFailureRepairs)}
      </text>
      <Show when={props.overlay}>
        <text fg="#778399">Run /harness again to close</text>
      </Show>
    </box>
  )
}

const tui: TuiPlugin = async (api) => {
  const [status, setStatus] = createSignal(initialStatus())
  const [overlay, setOverlay] = createSignal(false)
  const activeTools = new Set<string>()
  const openedScopes = new Set<string>()
  let observedTool = false
  let client: ProcessVerificationClient | undefined
  let clientPromise: Promise<ProcessVerificationClient> | undefined
  let observationChain: Promise<unknown> = Promise.resolve()
  let activeRootScopeId = ""

  const selectRootScope = (sessionId: string) => {
    let root = sessionId
    let current = api.state.session.get(root)
    while (current?.parentID) {
      root = current.parentID
      current = api.state.session.get(root)
    }
    if (activeRootScopeId && activeRootScopeId !== root && client) {
      void client.dispose()
      client = undefined
      clientPromise = undefined
      openedScopes.clear()
      setStatus(initialStatus())
    }
    activeRootScopeId = root
  }
  const rootScopeId = () => activeRootScopeId || status().rootScopeId || "root"
  const session = () => api.state.session.get(rootScopeId())
  const goal = () => session()?.title?.trim() || "Complete the current base-harness session"
  const currentSource = () =>
    goalSource(goal(), "session-" + rootScopeId(), "session_title")

  const ensureClient = async (): Promise<ProcessVerificationClient> => {
    if (client) return client
    if (!clientPromise) {
      const scopeId = rootScopeId()
      const runId = "tui-" + scopeId
      clientPromise = createVerificationClient({
        runId,
        scopeId,
        workspace: api.state.path.directory,
        goalSources: [currentSource()],
      }).then((value) => {
        client = value
        openedScopes.add(scopeId)
        value.subscribe(setStatus)
        return value
      })
    }
    return clientPromise
  }

  const notify = (title: string, message: string, variant = "info") => {
    api.ui.toast({
      title,
      message,
      variant: variant as "info" | "success" | "warning" | "error",
    })
  }

  const injectRepair = async (result: VerificationStatus) => {
    if (result.outcome !== "repair") return
    const prompt = [
      "Verifier rejected completion. Repair only the specified scope; do not rebuild the full plan.",
      "FailureKind: " + (result.failureKind ?? "verification_failed"),
      "Failed criterion: " + (result.failedCriterion ?? "unknown"),
      "Missing evidence: " + (result.missingEvidence?.join("; ") || "none reported"),
      "Repair scope: " + (result.repairScope ?? "current change"),
      "Repair count: " + String(result.repairCount ?? 0),
    ].join("\n")
    const id = rootScopeId()
    await api.client.session.prompt({
      sessionID: id,
      directory: api.state.path.directory,
      parts: [{ type: "text", text: prompt }],
    })
  }

  const verify = async (reason: "automatic" | "manual") => {
    try {
      await observationChain
      const verifier = await ensureClient()
      const result = await verifier.verify(reason)
      if (result.outcome === "ready") notify("Ready", "Independent verification passed.", "success")
      if (result.outcome === "blocked") {
        notify(
          "Verification blocked",
          result.message ?? "The same failure fingerprint exceeded its repair limit.",
          "error",
        )
      }
      await injectRepair(result)
    } catch (error) {
      notify(
        "Verifier unavailable",
        error instanceof Error ? error.message : String(error),
        "error",
      )
    }
  }

  api.command?.register((): TuiCommand[] => [
    {
      value: "harness.toggle",
      title: "Harness status",
      description: "Toggle the verification overlay",
      slash: { name: "harness" },
      category: "Harness",
      onSelect: () => setOverlay((value) => !value),
    },
    {
      value: "harness.goal",
      title: "GoalContract",
      description: "Show the active root goal",
      slash: { name: "goal" },
      category: "Harness",
      onSelect: () => notify("GoalContract", status().goal || goal()),
    },
    {
      value: "harness.verify",
      title: "Verify now",
      description: "Request independent verification",
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
      onSelect: () =>
        notify(
          "Evidence",
          String(status().evidenceRefs.length) +
            " trusted / " +
            String(status().candidateRefs.length) +
            " candidates",
        ),
    },
  ])

  api.slots.register({
    order: 50,
    slots: {
      sidebar_content: (_context, props) => {
        selectRootScope(props.session_id)
        return <VerificationPanel status={status()} />
      },
      app: () => (
        <Show when={overlay()}>
          <box
            position="absolute"
            top={2}
            right={2}
            zIndex={100}
          >
            <VerificationPanel status={status()} overlay />
          </box>
        </Show>
      ),
    },
  })

  api.event.on("message.part.updated", (event) => {
    const tool = toolState(event)
    if (!tool) return
    selectRootScope(tool.sessionId)
    const key = tool.sessionId + ":" + tool.callId
    if (tool.status === "pending" || tool.status === "running") {
      activeTools.add(key)
      return
    }
    if (tool.status !== "completed" && tool.status !== "error") return
    activeTools.delete(key)
    observedTool = true
    observationChain = observationChain.then(async () => {
      const verifier = await ensureClient()
      if (tool.tool === "harness_contract") {
        const proposal = tool.input as GoalContractProposal
        await verifier.proposeContract(materializeProposal(currentSource(), proposal))
        return
      }
      if (!openedScopes.has(tool.sessionId)) {
        const parent = api.state.session.get(tool.sessionId)?.parentID
        const parentScopeId = parent && openedScopes.has(parent) ? parent : rootScopeId()
        await verifier.openScope(tool.sessionId, parentScopeId)
        openedScopes.add(tool.sessionId)
      }
      await verifier.observe({
        scopeId: tool.sessionId,
        tool: tool.tool,
        status: tool.status === "completed" ? "completed" : "error",
        input: tool.input,
        output: tool.output,
        error: tool.error,
      })
    })
  })

  api.event.on("session.status", (event) => {
    const properties = event.properties
    const eventSessionId = text(properties?.sessionID)
    const state = record(properties?.status)
    if (!eventSessionId) return
    selectRootScope(eventSessionId)
    if (eventSessionId !== rootScopeId() || state?.type !== "idle") return
    if (!observedTool || activeTools.size > 0) return
    observedTool = false
    void verify("automatic")
  })

  api.event.on("session.error", (event) => {
    const eventSessionId = event.properties.sessionID
    if (!eventSessionId) return
    selectRootScope(eventSessionId)
    observedTool = true
    observationChain = observationChain.then(async () => {
      const verifier = await ensureClient()
      if (!openedScopes.has(eventSessionId)) {
        const parent = api.state.session.get(eventSessionId)?.parentID
        const parentScopeId = parent && openedScopes.has(parent) ? parent : rootScopeId()
        await verifier.openScope(eventSessionId, parentScopeId)
        openedScopes.add(eventSessionId)
      }
      await verifier.observe({
        scopeId: eventSessionId,
        tool: "model",
        status: "error",
        error: event.properties.error,
        metadata: {
          failureKind: classifyRuntimeFailure(event.properties.error),
        },
      })
    })
  })
}

export const VerificationPlugin: BuiltinTuiPlugin = {
  id: "internal:base-harness-verification",
  tui,
}
