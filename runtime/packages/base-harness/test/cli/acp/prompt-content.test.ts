import { describe, expect } from "bun:test"
import type { PromptResponse, SetSessionConfigOptionResponse } from "@agentclientprotocol/sdk"
import { Effect } from "effect"
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"
import { pathToFileURL } from "node:url"
import { cliIt } from "../../lib/cli-process"
import { expectOk } from "./acp-test-client"
import { createAcpClient, initialize, newSession, verifierConfig } from "./helpers"

const tinyPng = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="

describe("opencode acp prompt content subprocess", () => {
  cliIt.live(
    "accepts embedded text resource image and file resource link prompt content",
    ({ home, llm, opencode }) =>
      Effect.gen(function* () {
        const workspace = path.join(home, "workspace")
        yield* Effect.promise(() => mkdir(workspace))
        yield* Effect.promise(() => writeFile(path.join(workspace, "README.md"), "# ACP content smoke\n"))
        const acp = yield* createAcpClient(
          { opencode },
          { BASE_HARNESS_CONFIG_CONTENT: JSON.stringify(promptContentConfig(llm.url)) },
        )
        yield* initialize(acp)
        const session = yield* newSession(acp, workspace)
        const selected = expectOk(yield* acp.request<SetSessionConfigOptionResponse>("session/set_config_option", {
          sessionId: session.sessionId, configId: "effort", value: "high",
        }))
        expect(selected.configOptions.find((option) => option.id === "effort")?.currentValue).toBe("high")

        // The initial turn also requests a title from the local model fixture.
        yield* llm.text("ACP content smoke")
        yield* llm.text("embedded resource accepted")
        expectOk(
          yield* acp.request<PromptResponse>("session/prompt", {
            sessionId: session.sessionId,
            prompt: [
              { type: "text", text: "Use this embedded resource." },
              {
                type: "resource",
                resource: { uri: "file:///context.txt", mimeType: "text/plain", text: "embedded context" },
              },
            ],
          }),
        )

        const reset = expectOk(yield* acp.request<SetSessionConfigOptionResponse>("session/set_config_option", {
          sessionId: session.sessionId, configId: "effort", value: "provider_default",
        }))
        expect(reset.configOptions.find((option) => option.id === "effort")?.currentValue).toBe("provider_default")
        yield* llm.text("image accepted")
        expectOk(
          yield* acp.request<PromptResponse>("session/prompt", {
            sessionId: session.sessionId,
            prompt: [
              { type: "text", text: "Use this image." },
              {
                type: "image",
                mimeType: "image/png",
                data: tinyPng,
              },
            ],
          }),
        )

        const switched = expectOk(yield* acp.request<SetSessionConfigOptionResponse>("session/set_config_option", {
          sessionId: session.sessionId, configId: "model", value: "test/second-model",
        }))
        expect(switched.configOptions.find((option) => option.id === "effort")?.currentValue).toBe("provider_default")
        const maximum = expectOk(yield* acp.request<SetSessionConfigOptionResponse>("session/set_config_option", {
          sessionId: session.sessionId, configId: "effort", value: "max",
        }))
        expect(maximum.configOptions.find((option) => option.id === "effort")?.currentValue).toBe("max")
        yield* llm.text("file link accepted")
        const linked = expectOk(
          yield* acp.request<PromptResponse>("session/prompt", {
            sessionId: session.sessionId,
            prompt: [
              { type: "text", text: "Use this linked file." },
              {
                type: "resource_link",
                uri: pathToFileURL(path.join(workspace, "README.md")).href,
                name: "README.md",
                mimeType: "text/markdown",
              },
            ],
          }),
        )

        expect(linked.stopReason).toBe("end_turn")
        const inputs = yield* llm.inputs
        expect(inputs.some((input) => JSON.stringify(input).includes("embedded context"))).toBe(true)
        expect(inputs.some((input) => JSON.stringify(input).includes(tinyPng))).toBe(true)
        const workerInputs = inputs.filter((input) => Array.isArray(input.tools))
        expect(workerInputs.map((input) => input.reasoning_effort)).toEqual(["high", undefined, "max"])
        expect(workerInputs.map((input) => input.model)).toEqual(["test-model", "test-model", "second-model"])
      }),
    60_000,
  )

  cliIt.live(
    "rejects a workspace containing Host-private state before any model request",
    ({ home, llm, opencode }) => Effect.gen(function* () {
      const acp = yield* createAcpClient(
        { opencode }, { BASE_HARNESS_CONFIG_CONTENT: JSON.stringify(promptContentConfig(llm.url)) },
      )
      yield* initialize(acp)
      const session = yield* newSession(acp, home)
      const result = yield* acp.request<PromptResponse>("session/prompt", {
        sessionId: session.sessionId, prompt: [{ type: "text", text: "Read this workspace." }],
      })
      expect(result.error).toMatchObject({ code: -32603 })
      expect(result.result).toBeUndefined()
      expect(yield* llm.calls).toBe(0)
    }),
    60_000,
  )
})

function promptContentConfig(llmUrl: string) {
  const config = verifierConfig(llmUrl)
  return {
    ...config,
    provider: {
      test: {
        ...config.provider.test,
        models: Object.fromEntries(
          Object.entries(config.provider.test.models).map(([id, model]) => [
            id,
            {
              ...model,
              modalities: { input: ["text", "image"], output: ["text"] },
              attachment: true,
              reasoning: true,
            },
          ]),
        ),
      },
    },
  }
}
