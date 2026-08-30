import { afterEach, expect, test } from "bun:test"
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { tmpdir } from "node:os"
import { join } from "node:path"
import {
  SandboxError,
  SandboxManager,
  isolationPolicy,
  validateSandboxWorkspace,
} from "../src/sandbox"

const roots: string[] = []
afterEach(async () => {
  await Promise.all(roots.splice(0).map((root) => rm(root, { recursive: true, force: true })))
})

test("strict isolation defaults are deterministic", () => {
  expect(isolationPolicy()).toEqual({
    strictBackend: "auto",
    wslDistro: "Ubuntu-24.04",
    timeoutMs: 120_000,
    memoryMiB: 4096,
    maxProcesses: 128,
    maxOutputBytes: 10 * 1024 * 1024,
    maxInputBytes: 2 * 1024 * 1024 * 1024,
  })
})

test("workspace validation enforces input limits and Windows path policy", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-sandbox-validation-"))
  roots.push(workspace)
  await writeFile(join(workspace, "large.txt"), "12345", "utf8")

  await expect(validateSandboxWorkspace(workspace, 4)).rejects.toMatchObject({
    code: "SANDBOX_LIMIT_EXCEEDED",
  })
  if (process.platform === "win32") {
    await expect(validateSandboxWorkspace("\\\\server\\share", 1024)).rejects.toMatchObject({
      code: "SANDBOX_ESCAPE_ATTEMPT",
    })
  }
})

test.skipIf(process.platform !== "win32")(
  "WSL2 strict sandbox isolates filesystem and external network namespace",
  async () => {
    const workspace = await mkdtemp(join(tmpdir(), "base-harness-sandbox-wsl-"))
    roots.push(workspace)
    const target = join(workspace, "host.txt")
    await writeFile(target, "host-original", "utf8")

    const result = await new SandboxManager().run({
      workspace,
      cwd: workspace,
      command:
        'printf sandbox-ok; printf sandbox-copy > host.txt; test "$(find /sys/class/net -mindepth 1 -maxdepth 1 | wc -l)" -eq 1; if printf denied > /usr/bin/base-harness-probe 2>/dev/null; then exit 91; fi',
      config: {
        strictBackend: "wsl2",
        wslDistro: "Ubuntu-24.04",
        timeoutMs: 30_000,
        maxOutputBytes: 1024 * 1024,
        maxInputBytes: 16 * 1024 * 1024,
      },
    })

    expect(result.exitCode).toBe(0)
    expect(result.stdout).toContain("sandbox-ok")
    expect(result.provenance.backend).toBe("wsl2")
    expect(result.provenance.network).toBe("loopback_only")
    expect(await readFile(target, "utf8")).toBe("host-original")
  },
  60_000,
)

test.skipIf(process.platform !== "win32")("missing WSL distro fails closed", async () => {
  const workspace = await mkdtemp(join(tmpdir(), "base-harness-sandbox-missing-"))
  roots.push(workspace)
  await writeFile(join(workspace, "input.txt"), "input", "utf8")

  const error = await new SandboxManager()
    .run({
      workspace,
      cwd: workspace,
      command: "true",
      config: { strictBackend: "wsl2", wslDistro: "base-harness-missing-distro", timeoutMs: 5_000 },
    })
    .catch((value) => value)
  expect(error).toBeInstanceOf(SandboxError)
  expect(error.code).toBe("SANDBOX_UNAVAILABLE")
})
