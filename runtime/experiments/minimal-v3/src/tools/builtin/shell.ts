import type { ToolRegistry } from "../registry"
import { workspacePath } from "../path-policy"
import { ToolExecutionError } from "../types"

const cap = (value: string, limit = 1_000_000) => ({ text: value.slice(0, limit), truncated: value.length > limit })

function safeEnvironment(): Record<string, string> {
  const keys = ["PATH", "Path", "PATHEXT", "SystemRoot", "WINDIR", "HOME", "USERPROFILE", "TEMP", "TMP", "LANG", "LC_ALL", "TERM"]
  return Object.fromEntries(keys.flatMap((key) => process.env[key] ? [[key, process.env[key]!]] : []))
}

export function registerShellTools(registry: ToolRegistry): void {
  registry.register({
    name: "run_command", toolset: "shell", effect: "workspace_write", risk: "high",
    description: "Run a foreground process from an argv array inside the workspace. No shell string is evaluated.",
    parameters: {
      type: "object",
      properties: { argv: { type: "array", items: { type: "string" } }, cwd: { type: "string" }, timeoutMs: { type: "number" } },
      required: ["argv"], additionalProperties: false,
    },
    async execute(input, context) {
      const argv = input.argv
      if (!Array.isArray(argv) || !argv.length || !argv.every((item) => typeof item === "string" && item.length > 0)) throw new ToolExecutionError("argv must contain strings", "INVALID_COMMAND")
      const cwd = workspacePath(context.workspace, String(input.cwd ?? "."))
      const timeoutMs = Math.min(600_000, Math.max(100, Number(input.timeoutMs ?? 120_000)))
      const child = Bun.spawn(argv, { cwd, env: safeEnvironment(), stdout: "pipe", stderr: "pipe" })
      let timedOut = false
      const timer = setTimeout(() => { timedOut = true; child.kill() }, timeoutMs)
      const [stdout, stderr, exitCode] = await Promise.all([new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited]).finally(() => clearTimeout(timer))
      const result = { argv, cwd, exitCode, timedOut, stdout: cap(stdout), stderr: cap(stderr) }
      if (timedOut) throw new ToolExecutionError("Command timed out", "COMMAND_TIMEOUT", result)
      if (exitCode !== 0) throw new ToolExecutionError(`Command exited with code ${exitCode}`, "COMMAND_FAILED", result)
      return result
    },
  })
}
