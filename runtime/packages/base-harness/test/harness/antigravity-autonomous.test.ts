import { afterEach, expect, test } from "bun:test"
import { chmod, mkdtemp, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { AntigravityCli } from "../../src/harness/execution/antigravity-cli"
import { ExecutionBackends } from "../../src/harness/execution/backend-router"

const original = {
  binary: process.env.BASE_HARNESS_AGY_BINARY,
  useWsl: process.env.BASE_HARNESS_AGY_USE_WSL,
}

afterEach(() => {
  if (original.binary === undefined) delete process.env.BASE_HARNESS_AGY_BINARY
  else process.env.BASE_HARNESS_AGY_BINARY = original.binary
  if (original.useWsl === undefined) delete process.env.BASE_HARNESS_AGY_USE_WSL
  else process.env.BASE_HARNESS_AGY_USE_WSL = original.useWsl
})

test.skipIf(process.platform === "win32")(
  "built-in Antigravity adapter reports autonomous capability and authenticated usage from a controlled process",
  async () => {
    const root = await mkdtemp(join(tmpdir(), "base-harness-agy-autonomous-"))
    const binary = join(root, "agy-fixture")
    try {
      await writeFile(binary, `#!/bin/sh
if [ "$1" = "--help" ]; then
  printf '%s\n' 'agy fixture --effort (low|high)'
  exit 0
fi
if [ "$1" = "models" ]; then
  printf '%s\n' 'gemini-3.1-pro-high'
  exit 0
fi
cat >/dev/null
printf '%s\n' '{"event":"result","result":{"status":"SUCCESS","response":"fixture","usage":{"total_tokens":17}}}'
`, "utf8")
      await chmod(binary, 0o700)
      process.env.BASE_HARNESS_AGY_BINARY = binary
      process.env.BASE_HARNESS_AGY_USE_WSL = "0"

      const capabilities = await ExecutionBackends.discover(AntigravityCli.id)
      expect(capabilities).toMatchObject({
        models: ["gemini-3.1-pro-high"],
        autonomousDecision: { protocol: "autonomous-decision-v1", resourceUsage: "reported-v1" },
      })
      const result = await ExecutionBackends.execute({
        sessionID: "fixture-session",
        runId: "fixture-run",
        scopeID: "fixture-scope",
        phase: "autonomous_decision",
        workspace: root,
        prompt: "{}",
        selection: {
          kind: "agent_runtime",
          backendId: AntigravityCli.id,
          connectionId: AntigravityCli.id,
          modelId: "gemini-3.1-pro-high",
          nativeOptions: {},
          capabilityRevision: capabilities.revision,
        },
        mutationPolicy: "forbid",
        routeWrite: async () => { throw new Error("fixture must remain read-only") },
      })
      expect(result).toMatchObject({
        changedFiles: [],
        resourceUsage: { modelTokens: 17, costMinorUnits: 0 },
      })
      expect(result.output).toBe("fixture")
    } finally {
      await rm(root, { recursive: true, force: true })
    }
  },
)
