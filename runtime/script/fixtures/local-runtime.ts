import { mkdtemp, mkdir, writeFile, appendFile, readFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"

export async function createLocalRuntimeFixture(python: string, options: { interactive?: boolean; reasoner?: boolean; planned?: boolean; failIntegration?: boolean; repairWorker?: boolean; exhaustWorker?: boolean } = {}) {
  const scratch = await mkdtemp(path.join(tmpdir(), "base-harness-real-host-"))
  const workspace = path.join(scratch, "workspace")
  const state = path.join(scratch, "state")
  await mkdir(workspace)
  await mkdir(state)
  const target = path.join(workspace, "result-0.txt")
  let expected = "fixture success\n"
  const targets = options.planned ? [target, path.join(workspace, "result-1.txt"), ...(options.exhaustWorker ? [path.join(workspace, "result-2.txt")] : [])] : [target]
  const criterionIds = targets.map((_, index) => options.planned ? "criterion-" + index : "criterion")
  const claimIds = targets.map((_, index) => options.planned ? "claim-" + index : "claim")
  const marker = path.join(scratch, "mcp-calls.jsonl")
  let goal = options.exhaustWorker
    ? "Use the local MCP echo tool to obtain fixture success, then create result-0.txt, result-1.txt and result-2.txt, each containing exactly fixture success and a trailing newline, through independently verified WorkUnits."
    : options.planned
    ? "Use the local MCP echo tool to obtain fixture success, then create result-0.txt and result-1.txt, each containing exactly fixture success and a trailing newline, through independently verified WorkUnits."
    : "Use the local MCP echo tool to obtain fixture success, then create result-0.txt containing exactly fixture success and a trailing newline."
  const requestLog: Array<{ receivedAt: number; model?: string; stream: boolean; authenticated: boolean; tools: string[]; selected?: string; reasoningEffort?: unknown; reviewPhase?: string; workUnitId?: string; rootIntegration?: boolean; workerWriteAttempt?: number; injectedIncorrectContent?: boolean; workspaceBeforeRepair?: string | null }> = []
  const workerWrites = new Map<number, number>()
  let releaseIndependent!: () => void
  const independentStarted = new Promise<void>(resolve => { releaseIndependent = resolve })
  const exhaustionBarrier: { heldAt?: number; releasedAt?: number } = {}
  const token = "fixture-only-credential-not-a-real-key"
  let sequence = 0
  let httpSequence = 0
  let httpTraceTruncated = false
  const httpTrace: Array<{ id: number; receivedAt: number; method: string; path: string; handlerCompletedAt?: number; error?: string }> = []
  let pause: { entered: () => void; wait: Promise<void>; release: () => void } | undefined
  let stopHandler: (() => Promise<void>) | undefined
  const requestsPath = path.join(scratch, "model-requests.jsonl")
  
  const buildProposal = () => ({
    goal,
    criteria: targets.map((target, index) => ({
      criterionId: criterionIds[index], statement: path.basename(target) + " has the exact requested content",
      claimIds: [claimIds[index]], required: true, risk: "low",
    })),
    claims: targets.map((target, index) => ({
      claimId: claimIds[index], criterionIds: [criterionIds[index]], origin: "user",
      statement: path.basename(target) + " contains the requested content", kind: "artifact",
      scope: { targets: [target], capabilities: ["write"], exclusions: [] },
      applicability: { os: process.platform, provider: "fixture", model: options.reasoner ? "fixture-reasoner" : "fixture-model" },
      predicate: { type: "content_equals", value: expected },
      verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
    })),
    interpretation: { version: 1, candidates: [] },
  })
  const buildGraph = () => ({
    units: targets.map((target, index) => ({
      id: "unit-" + index, title: "Write " + path.basename(target),
      instructions: JSON.stringify({ protocol: "base-harness-fixture-work-unit-v1", workUnitId: "unit-" + index, target, expected }),
      agentType: "general", claimIds: [claimIds[index]], criterionIds: [criterionIds[index]],
      dependsOn: [], readSet: [path.basename(target)], writeSet: [path.basename(target)], integrationRequests: [],
    })),
    integrationPaths: [],
  })

  const server = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const reception: (typeof httpTrace)[number] = {
        id: ++httpSequence, receivedAt: Date.now(), method: request.method, path: new URL(request.url).pathname,
      }
      if (httpTrace.length < 4096) httpTrace.push(reception)
      else httpTraceTruncated = true
      try {
        if (new URL(request.url).pathname === "/__fixture/stop") {
          if (request.method !== "POST" || request.headers.get("x-fixture-key") !== token) {
            return new Response("Denied", { status: 403 })
          }
          setTimeout(() => { void stopHandler?.() }, 10)
          return Response.json({ stopping: true })
        }
        if (new URL(request.url).pathname === "/v1/models") {
          return Response.json({ object: "list", data: [{ id: "fixture-model", object: "model", owned_by: "fixture" }, { id: "fixture-reasoner", object: "model", owned_by: "fixture", supported_reasoning_efforts: ["high", "max"] }] })
        }
        if (request.method !== "POST" || !new URL(request.url).pathname.endsWith("/chat/completions")) {
          return new Response("Unsupported fixture route", { status: 404 })
        }
        const body: any = await request.json()
        if (request.headers.get("authorization") !== "Bearer " + token) {
          await appendFile(requestsPath, JSON.stringify({ authenticated: false, model: body.model }) + "\n")
          return Response.json({ error: { message: "Connect the local fixture credential first", type: "authentication_error", code: "invalid_api_key" } }, { status: 401 })
        }
        const names: string[] = (body.tools ?? []).map((tool: any) => tool.function?.name).filter(Boolean)
        const completed = new Set<string>()
        const messages: any[] = body.messages ?? []
        const latestUser = messages.findLastIndex(message => message.role === "user")
        const turn = messages.slice(Math.max(0, latestUser))
        for (const message of turn) {
          for (const call of message.tool_calls ?? []) if (call.function?.name) completed.add(call.function.name)
        }
        const texts = turn.map((message: any) => typeof message.content === "string"
          ? message.content
          : Array.isArray(message.content) ? message.content.map((part: any) => part.text ?? "").join("\n") : "").join("\n")
        const reviewPhase = options.planned && texts.includes('"protocol":"base-harness-meta-review-v1"')
          ? texts.includes('"phase":"goal_contract"') ? "goal_contract" : "plan" : undefined
        const rootIntegration = !!(options.planned && !reviewPhase && texts.includes('"protocol":"base-harness-root-integration-v1"'))
        // Repair prompts intentionally omit original instructions; identify this fixture's
        // WorkUnit from its retained user-message history, not from production policy.
        const workerTexts = options.repairWorker || options.exhaustWorker
          ? messages.filter(message => message.role === "user").map(message => typeof message.content === "string"
            ? message.content : Array.isArray(message.content) ? message.content.map((part: any) => part.text ?? "").join("\n") : "").join("\n")
          : texts
        const workerIndex = options.planned && !reviewPhase && !rootIntegration
          ? targets.findIndex((_, index) => workerTexts.includes('"workUnitId":"unit-' + index + '"')) : -1
        let selected: string | undefined
        let args: unknown
        let workerWriteAttempt: number | undefined
        let injectedIncorrectContent: boolean | undefined
        let workspaceBeforeRepair: string | null | undefined
        if (reviewPhase || rootIntegration) {
          // Typed Host protocol markers select this deterministic fixture response, not production policy.
        } else if (workerIndex >= 0) {
          if (names.includes("write") && !completed.has("write")) {
            selected = "write"
            workerWriteAttempt = (workerWrites.get(workerIndex) ?? 0) + 1
            workerWrites.set(workerIndex, workerWriteAttempt)
            injectedIncorrectContent = !!(workerIndex === 0 && (options.exhaustWorker || (options.repairWorker && workerWriteAttempt === 1)))
            if ((options.repairWorker || options.exhaustWorker) && workerIndex === 0 && workerWriteAttempt > 1) {
              try {
                workspaceBeforeRepair = await readFile(targets[workerIndex], "utf8")
              } catch (error) {
                if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error
                workspaceBeforeRepair = null
              }
            }
            args = { filePath: targets[workerIndex], content: injectedIncorrectContent ? "fixture incorrect\n" : expected }
          }
        } else if (names.includes("harness_contract")) {
          if (!completed.has("harness_contract")) {
            selected = "harness_contract"
            const proposal = buildProposal()
            args = { ...proposal, claims: proposal.claims.map(claim => ({
              ...claim, applicability: { ...claim.applicability, model: body.model },
            })) }
          } else {
            const echo = names.find((name) => name.includes("fixture") && name.endsWith("echo"))
            if (echo && !completed.has(echo)) {
              selected = echo
              args = { message: expected.trimEnd() }
            } else if (options.planned) {
              if (names.includes("harness_workgraph") && !completed.has("harness_workgraph")) {
                selected = "harness_workgraph"
                args = buildGraph()
              }
            } else if (names.includes("write") && !completed.has("write")) {
              selected = "write"
              args = { filePath: target, content: expected }
            }
          }
        }
        requestLog.push({
          receivedAt: reception.receivedAt, model: body.model, stream: body.stream === true,
          authenticated: request.headers.get("authorization") === "Bearer " + token,
          tools: names, selected, reasoningEffort: body.reasoning_effort,
          reviewPhase, workUnitId: workerIndex >= 0 ? "unit-" + workerIndex : undefined, rootIntegration,
          workerWriteAttempt, injectedIncorrectContent, workspaceBeforeRepair,
        })
        await appendFile(requestsPath, JSON.stringify(requestLog.at(-1)) + "\n")
        if (options.exhaustWorker && workerIndex === 2 && exhaustionBarrier.releasedAt === undefined) {
          exhaustionBarrier.releasedAt = Date.now()
          releaseIndependent()
        }
        if (options.exhaustWorker && workerIndex === 1 && selected === "write") {
          exhaustionBarrier.heldAt = Date.now()
          // Keep the second slot occupied until the queued independent unit starts.
          // The diagnostic's overall deadline bounds a scheduler deadlock.
          await independentStarted
        }
        if (pause && !reviewPhase && !rootIntegration && workerIndex < 0 && names.includes("harness_contract")) {
          const held = pause
          held.entered()
          await held.wait
          if (pause === held) pause = undefined
        }
        if (rootIntegration && options.failIntegration) {
          return Response.json({ error: {
            message: "Injected root integration provider failure",
            type: "invalid_request_error", code: "fixture_integration_failure",
          } }, { status: 400 })
        }
        const call = selected ? {
          id: "fixture-call-" + (++sequence), type: "function",
          function: { name: selected, arguments: JSON.stringify(args) },
        } : undefined
        const content = reviewPhase
          ? JSON.stringify({ phase: reviewPhase, outcome: "pass", issues: [] })
          : rootIntegration ? "Root integration finished. The Host must independently verify completion."
          : options.planned && workerIndex < 0 && names.includes("harness_contract")
            ? "The plan has been submitted to the Host. Follow its typed planning and verification status."
          : names.includes("harness_contract") || workerIndex >= 0
            ? "The requested artifact has been written. The Host must independently verify completion."
            : "Fixture task"
        const id = "fixture-completion-" + (++sequence)
        const base = { id, created: Math.floor(Date.now() / 1000), model: body.model ?? "fixture-model" }
        if (!body.stream) return Response.json({
          ...base, object: "chat.completion",
          choices: [{ index: 0, message: { role: "assistant", content: call ? null : content, ...(call ? { tool_calls: [call] } : {}) },
            finish_reason: call ? "tool_calls" : "stop" }],
          usage: { prompt_tokens: 16, completion_tokens: 16, total_tokens: 32 },
        })
        const chunk = (delta: unknown, finish: string | null = null) => ({
          ...base, object: "chat.completion.chunk",
          choices: [{ index: 0, delta, finish_reason: finish }],
        })
        const delta = call
          ? { role: "assistant", tool_calls: [{ index: 0, ...call }] }
          : { role: "assistant", content }
        const output = [
          chunk(delta), chunk({}, call ? "tool_calls" : "stop"),
          { ...base, object: "chat.completion.chunk", choices: [],
            usage: { prompt_tokens: 16, completion_tokens: 16, total_tokens: 32 } },
        ].map((entry) => "data: " + JSON.stringify(entry) + "\n\n").join("") + "data: [DONE]\n\n"
        return new Response(output, { headers: { "content-type": "text/event-stream", "cache-control": "no-cache" } })
      } catch (error) {
        reception.error = (error instanceof Error ? error.name + ": " + error.message : String(error)).slice(0,512)
        throw error
      } finally {
        // Handler completion is response preparation, not proof of delivery to the client.
        reception.handlerCompletedAt = Date.now()
      }
    },
  })
  
  const mcpProgram = [
    "import json,sys,os",
    "marker=sys.argv[1]",
    "for line in sys.stdin:",
    " try:",
    "  request=json.loads(line)",
    "  with open(marker+\'.lifecycle.jsonl\',\'a\',encoding=\'utf-8\') as audit: audit.write(json.dumps({\'method\':request.get(\'method\'),\'pid\':os.getpid()})+\'\\n\')",
    "  if 'id' not in request: continue",
    "  method=request.get('method')",
    "  if method=='initialize':",
    "   result={'protocolVersion':request['params']['protocolVersion'],'capabilities':{'tools':{}},'serverInfo':{'name':'fixture','version':'1'}}",
    "  elif method=='tools/list':",
    "   result={'tools':[{'name':'echo','description':'Read-only local echo fixture','inputSchema':{'type':'object','properties':{'message':{'type':'string'}},'required':['message']},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True,'openWorldHint':False}}]}",
    "  elif method=='tools/call':",
    "   with open(marker,'a',encoding='utf-8') as output: output.write(json.dumps(request['params'])+'\\n')",
    "   result={'content':[{'type':'text','text':request['params']['arguments']['message']}],'isError':False}",
    "  elif method=='ping': result={}",
    "  else:",
    "   print(json.dumps({'jsonrpc':'2.0','id':request['id'],'error':{'code':-32601,'message':'Unsupported method'}}),flush=True)",
    "   continue",
    "  print(json.dumps({'jsonrpc':'2.0','id':request['id'],'result':result}),flush=True)",
    " except Exception as error: print(str(error),file=sys.stderr,flush=True)",
  ].join("\n")
  
  await writeFile(path.join(workspace, "base-harness.jsonc"), JSON.stringify({
    enabled_providers: ["fixture"],
    model: "fixture/fixture-model",
    small_model: "fixture/fixture-model",
    provider: {
      fixture: {
        npm: "@ai-sdk/openai-compatible", name: "Local fixture",
        options: { baseURL: "http://127.0.0.1:" + server.port + "/v1", ...(options.interactive ? {} : { apiKey: token }) },
        models: {
          "fixture-model": { name: "Fixture model", limit: { context: 32768, output: 8192 } },
          ...(options.interactive || options.reasoner ? {
            "fixture-reasoner": {
              name: "Fixture reasoner", reasoning: true, limit: { context: 32768, output: 8192 },
              variants: { high: { reasoningEffort: "high" }, max: { reasoningEffort: "max" } },
            },
          } : {}),
        },
      },
    },
    mcp: { fixture: { type: "local", command: [python, "-u", "-c", mcpProgram, marker], enabled: true } },
    kernel: { defaultDomain: "develop" },
    verification: { profile: "adaptive", trigger: "auto", maxSameFailureRepairs: 2 },
  }, null, 2))
  
  return {
    scratch, workspace, state, target, targets, criterionIds, claimIds, marker, token, requestLog, requestsPath,
    httpTrace, exhaustionBarrier,
    get httpTraceTruncated() { return httpTraceTruncated },
    get expected() { return expected },
    get goal() { return goal },
    reviseGoal() {
      if (!options.planned) throw new Error("Revision fixture requires planned work")
      expected = "fixture revised success\n"
      goal = "Use the local MCP echo tool to obtain fixture revised success, then create result-0.txt and result-1.txt, each containing exactly fixture revised success and a trailing newline, through independently verified WorkUnits."
    },
    pauseNextPlanningRequest() {
      if (pause) throw new Error("A planning request is already paused")
      let entered!: () => void, release!: () => void
      const observed = new Promise<void>(resolve => { entered = resolve })
      const wait = new Promise<void>(resolve => { release = resolve })
      pause = { entered, wait, release }
      return { entered: observed, release }
    },
    modelURL: "http://127.0.0.1:" + server.port,
    env: {
      ...process.env,
      BASE_HARNESS_PYTHON: python, BASE_HARNESS_LAUNCH_CWD: workspace,
      BASE_HARNESS_DISABLE_MODELS_FETCH: "true", BASE_HARNESS_SERVER_PASSWORD: "",
      APPDATA: state, LOCALAPPDATA: state,
      XDG_CONFIG_HOME: state, XDG_DATA_HOME: state, XDG_STATE_HOME: state, XDG_CACHE_HOME: state,
    },
    onStop(callback: () => Promise<void>) { stopHandler = callback },
    stop() { releaseIndependent(); pause?.release(); pause = undefined; server.stop(true) },
  }
}
