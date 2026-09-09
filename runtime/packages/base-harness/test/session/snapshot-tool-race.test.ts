/**
 * Guard pre-tool snapshot capture when the model responds with an instant write.
 * Accept the real contract before the first model/tool step so admission remains
 * active without adding an earlier model step that could conceal the race.
 * A structured write exercises the same tool dispatch without a POSIX shell.
 */
import { expect } from "bun:test"
import { Effect, Layer } from "effect"
import { LayerNode } from "@base-harness/core/effect/layer-node"
import fs from "fs/promises"
import path from "path"
import { Session } from "@/session/session"
import { SessionPrompt } from "../../src/session/prompt"
import { SessionSummary } from "../../src/session/summary"
import { MessageV2 } from "../../src/session/message-v2"
import { SessionV1 } from "@base-harness/core/v1/session"
import { Database } from "@base-harness/core/database/database"
import { SessionProjector } from "@base-harness/core/session/projector"
import { provideTmpdirServer } from "../fixture/fixture"
import { testEffect } from "../lib/effect"
import { TestLLMServer } from "../lib/llm-server"

import { LSP } from "@/lsp/lsp"
import { MCP } from "../../src/mcp"
import { CrossSpawnSpawner } from "@base-harness/core/cross-spawn-spawner"
import { RuntimeFlags } from "@/effect/runtime-flags"
import { registerHarnessContractProposal } from "@/tool/harness-contract-state"
import { Coordinator } from "@/harness/coordinator-service"

const mcp = Layer.succeed(
  MCP.Service,
  MCP.Service.of({
    status: () => Effect.succeed({}),
    clients: () => Effect.succeed({}),
    instructions: () => Effect.succeed([]),
    tools: () => Effect.succeed({}),
    prompts: () => Effect.succeed({}),
    resources: () => Effect.succeed({}),
    resourceTemplates: () => Effect.succeed({}),
    add: () => Effect.succeed({ status: { status: "disabled" as const } }),
    connect: () => Effect.void,
    disconnect: () => Effect.void,
    getPrompt: () => Effect.succeed(undefined),
    readResource: () => Effect.succeed(undefined),
    startAuth: () => Effect.die("unexpected MCP auth"),
    authenticate: () => Effect.die("unexpected MCP auth"),
    finishAuth: () => Effect.die("unexpected MCP auth"),
    removeAuth: () => Effect.void,
    supportsOAuth: () => Effect.succeed(false),
    hasStoredTokens: () => Effect.succeed(false),
    getAuthStatus: () => Effect.succeed("not_authenticated" as const),
  }),
)

const lsp = Layer.succeed(
  LSP.Service,
  LSP.Service.of({
    init: () => Effect.void,
    status: () => Effect.succeed([]),
    hasClients: () => Effect.succeed(false),
    touchFile: () => Effect.void,
    diagnostics: () => Effect.succeed({}),
    hover: () => Effect.succeed(undefined),
    definition: () => Effect.succeed([]),
    references: () => Effect.succeed([]),
    implementation: () => Effect.succeed([]),
    documentSymbol: () => Effect.succeed([]),
    workspaceSymbol: () => Effect.succeed([]),
    prepareCallHierarchy: () => Effect.succeed([]),
    incomingCalls: () => Effect.succeed([]),
    outgoingCalls: () => Effect.succeed([]),
  }),
)

const root = LayerNode.group([
  SessionPrompt.node,
  Session.node,
  SessionProjector.node,
  SessionSummary.node,
  Database.node,
  CrossSpawnSpawner.node,
  LayerNode.make({ service: TestLLMServer, layer: TestLLMServer.layer, deps: [] }),
])
const it = testEffect(
  LayerNode.compile(root, [
    [MCP.node, mcp],
    [LSP.node, lsp],
    [RuntimeFlags.node, RuntimeFlags.layer({ experimentalEventSystem: true })],
  ]),
)

const providerCfg = (url: string) => ({
  provider: {
    test: {
      name: "Test",
      id: "test",
      env: [],
      npm: "@ai-sdk/openai-compatible",
      models: {
        "test-model": {
          id: "test-model",
          name: "Test Model",
          attachment: false,
          reasoning: false,
          temperature: false,
          tool_call: true,
          release_date: "2025-01-01",
          limit: { context: 100000, output: 10000 },
          cost: { input: 0, output: 0 },
          options: {},
        },
      },
      options: {
        apiKey: "test-key",
        baseURL: url,
      },
    },
  },
})

it.live("tool execution produces non-empty session diff (snapshot race)", () =>
  provideTmpdirServer(
    Effect.fnUntraced(function* ({ dir, llm }) {
      const prompt = yield* SessionPrompt.Service
      const sessions = yield* Session.Service
      const summary = yield* SessionSummary.Service

      const session = yield* sessions.create({
        title: "snapshot race test",
        permission: [{ permission: "*", pattern: "*", action: "allow" }],
      })

      const filePath = path.join(dir, "race-test.txt")
      const expected = "snapshot race test content\n"
      yield* Effect.addFinalizer(() =>
        Effect.promise(() => Coordinator.cancel(session.id)).pipe(Effect.ignore),
      )
      yield* llm.tool("write", { filePath, content: expected })
      yield* llm.text("done")

      // Seed user message
      yield* prompt.prompt({
        sessionID: session.id,
        agent: "build",
        noReply: true,
        parts: [{ type: "text", text: "create the file" }],
      })

      // Host contract admission precedes the first instant mutation response.
      const admission = yield* Effect.promise(() => registerHarnessContractProposal(session.id, {
        goal: "create the file",
        interpretation: { version: 1, candidates: [] },
        criteria: [{
          criterionId: "race-content", statement: "The file contains the requested content",
          claimIds: ["race-file"], required: true, risk: "low",
        }],
        claims: [{
          claimId: "race-file", criterionIds: ["race-content"], origin: "user",
          statement: "race-test.txt contains the requested content", kind: "artifact",
          scope: { targets: [filePath], capabilities: ["write"], exclusions: [] },
          applicability: { os: process.platform, provider: "test", model: "test-model" },
          predicate: { type: "content_equals", value: expected },
          verifierPolicy: { minimumStrength: "structural", allowedVerifierIds: ["file"], minIndependentFamilies: 1 },
        }],
      }))
      expect(admission.contractStatus).toBe("accepted")
      expect(admission.planningState).toBe("executing")
      expect(yield* Effect.promise(() => fs.access(filePath).then(() => true, () => false))).toBe(false)

      // Run the agent loop
      const result = yield* prompt.loop({ sessionID: session.id })
      expect(result.info.role).toBe("assistant")

      // Verify the file was created
      const fileExists = yield* Effect.promise(() =>
        fs
          .access(filePath)
          .then(() => true)
          .catch(() => false),
      )
      expect(fileExists).toBe(true)
      expect(yield* Effect.promise(() => fs.readFile(filePath, "utf8"))).toBe(expected)

      // Verify the tool call completed (in the first assistant message)
      const allMsgs = yield* MessageV2.filterCompactedEffect(session.id)
      const user = allMsgs.find(
        (msg): msg is SessionV1.WithParts & { info: SessionV1.User } => msg.info.role === "user",
      )
      const tool = allMsgs
        .flatMap((m) => m.parts)
        .find((p): p is SessionV1.ToolPart => p.type === "tool" && p.tool === "write")
      expect(tool?.state.status).toBe("completed")
      if (!user) throw new Error("Expected user message")

      // Poll for the turn diff — summarize() is fire-and-forget.
      let diff: Array<{ file?: string }> = []
      for (let i = 0; i < 50; i++) {
        diff = yield* summary.diff({ sessionID: session.id, messageID: user.info.id })
        if (diff.length > 0) break
        yield* Effect.sleep("100 millis")
      }
      expect(diff.length).toBeGreaterThan(0)
      expect(diff.some((item) => item.file?.replaceAll("\\", "/").endsWith("race-test.txt"))).toBe(true)
    }),
    { git: true, config: providerCfg },
  ),
)
