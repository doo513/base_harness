import { randomUUID } from "node:crypto"
import { promises as fs } from "node:fs"
import os from "node:os"
import path from "node:path"

export type SandboxBackendName = "wsl2" | "namespace"

export interface IsolationConfig {
  strictBackend?: "auto" | SandboxBackendName
  wslDistro?: string
  timeoutMs?: number
  memoryMiB?: number
  maxProcesses?: number
  maxOutputBytes?: number
  maxInputBytes?: number
}

export interface SandboxPolicy {
  strictBackend: "auto" | SandboxBackendName
  wslDistro: string
  timeoutMs: number
  memoryMiB: number
  maxProcesses: number
  maxOutputBytes: number
  maxInputBytes: number
}

export interface SandboxProvenance {
  backend: SandboxBackendName
  containment: "user_mount_pid_net_namespace"
  network: "loopback_only"
  state: "completed" | "failed"
  distro?: string
  kernel?: string
  timeoutMs: number
  memoryMiB: number
  maxProcesses: number
  maxOutputBytes: number
  inputBytes: number
  workspaceHash?: string
  code?: string
}

export interface SandboxRequest {
  command: string
  workspace: string
  cwd: string
  config?: IsolationConfig
  signal?: AbortSignal
}

export interface SandboxResult {
  exitCode: number
  stdout: string
  stderr: string
  provenance: SandboxProvenance
}

export class SandboxError extends Error {
  constructor(
    readonly code:
      | "SANDBOX_UNAVAILABLE"
      | "SANDBOX_POLICY_DENIED"
      | "SANDBOX_LIMIT_EXCEEDED"
      | "SANDBOX_ESCAPE_ATTEMPT",
    message: string,
    readonly provenance?: Partial<SandboxProvenance>,
  ) {
    super(message)
    this.name = "SandboxError"
  }
}

export const isolationPolicy = (input: IsolationConfig = {}): SandboxPolicy => ({
  strictBackend: input.strictBackend ?? "auto",
  wslDistro: input.wslDistro ?? "Ubuntu-24.04",
  timeoutMs: input.timeoutMs ?? 120_000,
  memoryMiB: input.memoryMiB ?? 4096,
  maxProcesses: input.maxProcesses ?? 128,
  maxOutputBytes: input.maxOutputBytes ?? 10 * 1024 * 1024,
  maxInputBytes: input.maxInputBytes ?? 2 * 1024 * 1024 * 1024,
})

const canonical = (value: string) => (process.platform === "win32" ? value.toLowerCase() : value)
const inside = (parent: string, child: string) => {
  const relative = path.relative(canonical(parent), canonical(child))
  return relative === "" || (!relative.startsWith(".." + path.sep) && relative !== ".." && !path.isAbsolute(relative))
}

export async function validateSandboxWorkspace(workspace: string, maxInputBytes: number) {
  if (process.platform === "win32" && (/^\\\\[?.]\\/.test(workspace) || /^\\\\/.test(workspace))) {
    throw new SandboxError("SANDBOX_ESCAPE_ATTEMPT", "UNC and Windows device paths are not valid sandbox roots")
  }
  const root = await fs.realpath(workspace).catch(() => {
    throw new SandboxError("SANDBOX_UNAVAILABLE", "Sandbox workspace does not exist")
  })
  let bytes = 0
  const visit = async (directory: string): Promise<void> => {
    for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name)
      const stat = await fs.lstat(target)
      if (stat.isSymbolicLink()) {
        const resolved = await fs.realpath(target).catch(() => "")
        if (!resolved || !inside(root, resolved)) {
          throw new SandboxError("SANDBOX_ESCAPE_ATTEMPT", `Sandbox link escapes workspace: ${target}`)
        }
        continue
      }
      if (stat.isDirectory()) await visit(target)
      else if (stat.isFile()) bytes += stat.size
      else throw new SandboxError("SANDBOX_ESCAPE_ATTEMPT", `Unsupported sandbox filesystem entry: ${target}`)
      if (bytes > maxInputBytes) {
        throw new SandboxError("SANDBOX_LIMIT_EXCEEDED", "Sandbox input exceeds configured maxInputBytes")
      }
    }
  }
  await visit(root)
  return { root, bytes }
}

type Capture = { code: number; stdout: string; stderr: string }

async function execute(
  argv: string[],
  options: { cwd?: string; timeoutMs: number; maxOutputBytes: number; signal?: AbortSignal },
): Promise<Capture> {
  const child = Bun.spawn(argv, {
    cwd: options.cwd,
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
    env: process.env,
  })
  let exceeded = false
  let timedOut = false
  const read = async (stream: ReadableStream<Uint8Array>) => {
    const reader = stream.getReader()
    const chunks: Uint8Array[] = []
    let size = 0
    while (true) {
      const next = await reader.read()
      if (next.done) break
      size += next.value.byteLength
      if (size > options.maxOutputBytes) {
        exceeded = true
        child.kill()
        break
      }
      chunks.push(next.value)
    }
    return Buffer.concat(chunks).toString("utf8")
  }
  const abort = () => child.kill()
  options.signal?.addEventListener("abort", abort, { once: true })
  const timer = setTimeout(() => {
    timedOut = true
    child.kill()
  }, options.timeoutMs + 5_000)
  try {
    const [code, stdout, stderr] = await Promise.all([
      child.exited,
      read(child.stdout as ReadableStream<Uint8Array>),
      read(child.stderr as ReadableStream<Uint8Array>),
    ])
    if (exceeded) throw new SandboxError("SANDBOX_LIMIT_EXCEEDED", "Sandbox output exceeded maxOutputBytes")
    if (timedOut) throw new SandboxError("SANDBOX_LIMIT_EXCEEDED", "Sandbox process exceeded timeoutMs")
    if (options.signal?.aborted) throw new SandboxError("SANDBOX_POLICY_DENIED", "Sandbox execution was cancelled")
    return { code, stdout, stderr }
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener("abort", abort)
  }
}

const runner = String.raw`
root=$1
workspace=$2
workdir=$3
seconds=$4
memory=$5
processes=$6
filesize=$7
command=$8
mount -t tmpfs -o mode=755 tmpfs "$root"
mkdir -p "$root/bin" "$root/usr" "$root/lib" "$root/lib64" "$root/etc" "$root/dev" "$root/proc" "$root/sys" "$root/tmp" "$root/workspace"
for source in /bin /usr /lib /lib64 /etc /dev /sys; do
  [ -e "$source" ] || continue
  mount --rbind "$source" "$root$source"
  mount -o remount,ro,bind "$root$source"
done
mount --bind "$workspace" "$root/workspace"
mount -o remount,rw,bind "$root/workspace"
mount -t proc proc "$root/proc"
mount -t tmpfs -o mode=1777 tmpfs "$root/tmp"
mkdir -p "$root/tmp/home"
ip link set lo up
exec chroot "$root" /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/tmp/home TMPDIR=/tmp LANG=C.UTF-8 LC_ALL=C.UTF-8 TERM=dumb /usr/bin/prlimit --as="$memory" --nproc="$processes" --fsize="$filesize" --cpu="$seconds" /usr/bin/timeout --signal=TERM --kill-after=5s "$seconds"s /usr/bin/setsid /bin/sh -lc "cd \"$workdir\" && exec /bin/sh -lc \"\$1\"" sandbox-command "$command"
`

const safeId = () => randomUUID().replaceAll("-", "")

async function checked(argv: string[], timeoutMs = 30_000) {
  const result = await execute(argv, { timeoutMs, maxOutputBytes: 1024 * 1024 })
  if (result.code !== 0) {
    throw new SandboxError("SANDBOX_UNAVAILABLE", result.stderr.trim() || `Sandbox setup failed: ${argv[0]}`)
  }
  return result.stdout.trim()
}

async function wslRun(request: SandboxRequest, policy: SandboxPolicy, root: string, inputBytes: number) {
  const prefix = ["wsl.exe", "-d", policy.wslDistro, "--exec"]
  const probe = await checked([...prefix, "/bin/sh", "-lc", "command -v unshare prlimit timeout setsid mount chroot ip >/dev/null && uname -r"])
  const home = await checked([...prefix, "/bin/sh", "-lc", 'printf %s "$HOME"'])
  const source = await checked([...prefix, "/usr/bin/wslpath", "-a", root])
  const id = safeId()
  const base = `${home}/.local/state/base-harness/sandboxes/${id}`
  const workspace = `${base}/workspace`
  const mountRoot = `${base}/root`
  const relative = path.relative(root, request.cwd).replaceAll("\\", "/")
  if (relative === ".." || relative.startsWith("../") || path.isAbsolute(relative)) {
    throw new SandboxError("SANDBOX_ESCAPE_ATTEMPT", "Sandbox working directory is outside workspace")
  }
  const workdir = relative ? `/workspace/${relative}` : "/workspace"
  try {
    await checked([...prefix, "/bin/mkdir", "-p", workspace, mountRoot])
    await checked([...prefix, "/bin/cp", "-a", "--no-preserve=links", `${source}/.`, workspace], Math.max(30_000, policy.timeoutMs))
    const seconds = Math.max(1, Math.ceil(policy.timeoutMs / 1000))
    const result = await execute(
      [
        ...prefix,
        "/usr/bin/unshare",
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "--net",
        "/bin/sh",
        "-eu",
        "-c",
        runner,
        "sandbox-runner",
        mountRoot,
        workspace,
        workdir,
        String(seconds),
        String(policy.memoryMiB * 1024 * 1024),
        String(policy.maxProcesses),
        String(512 * 1024 * 1024),
        request.command,
      ],
      { timeoutMs: policy.timeoutMs, maxOutputBytes: policy.maxOutputBytes, signal: request.signal },
    )
    return {
      exitCode: result.code,
      stdout: result.stdout,
      stderr: result.stderr,
      provenance: {
        backend: "wsl2" as const,
        containment: "user_mount_pid_net_namespace" as const,
        network: "loopback_only" as const,
        state: "completed" as const,
        distro: policy.wslDistro,
        kernel: probe,
        timeoutMs: policy.timeoutMs,
        memoryMiB: policy.memoryMiB,
        maxProcesses: policy.maxProcesses,
        maxOutputBytes: policy.maxOutputBytes,
        inputBytes,
      },
    }
  } finally {
    if (base.startsWith(`${home}/.local/state/base-harness/sandboxes/`)) {
      await execute([...prefix, "/bin/rm", "-rf", "--", base], { timeoutMs: 30_000, maxOutputBytes: 1024 * 1024 }).catch(() => undefined)
    }
  }
}

async function namespaceRun(request: SandboxRequest, policy: SandboxPolicy, root: string, inputBytes: number) {
  if (process.platform === "win32") throw new SandboxError("SANDBOX_UNAVAILABLE", "Linux namespace backend is unavailable on Windows")
  const id = safeId()
  const base = path.join(process.env.XDG_STATE_HOME ?? path.join(os.homedir(), ".local", "state"), "base-harness", "sandboxes", id)
  const workspace = path.join(base, "workspace")
  const mountRoot = path.join(base, "root")
  const relative = path.relative(root, request.cwd)
  if (relative === ".." || relative.startsWith(".." + path.sep) || path.isAbsolute(relative)) {
    throw new SandboxError("SANDBOX_ESCAPE_ATTEMPT", "Sandbox working directory is outside workspace")
  }
  await fs.mkdir(mountRoot, { recursive: true })
  await fs.cp(root, workspace, { recursive: true, dereference: false, verbatimSymlinks: true })
  const seconds = Math.max(1, Math.ceil(policy.timeoutMs / 1000))
  try {
    const result = await execute(
      [
        "unshare",
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "--net",
        "/bin/sh",
        "-eu",
        "-c",
        runner,
        "sandbox-runner",
        mountRoot,
        workspace,
        relative ? `/workspace/${relative.replaceAll(path.sep, "/")}` : "/workspace",
        String(seconds),
        String(policy.memoryMiB * 1024 * 1024),
        String(policy.maxProcesses),
        String(512 * 1024 * 1024),
        request.command,
      ],
      { timeoutMs: policy.timeoutMs, maxOutputBytes: policy.maxOutputBytes, signal: request.signal },
    )
    return {
      exitCode: result.code,
      stdout: result.stdout,
      stderr: result.stderr,
      provenance: {
        backend: "namespace" as const,
        containment: "user_mount_pid_net_namespace" as const,
        network: "loopback_only" as const,
        state: "completed" as const,
        kernel: os.release(),
        timeoutMs: policy.timeoutMs,
        memoryMiB: policy.memoryMiB,
        maxProcesses: policy.maxProcesses,
        maxOutputBytes: policy.maxOutputBytes,
        inputBytes,
      },
    }
  } finally {
    await fs.rm(base, { recursive: true, force: true })
  }
}

export class SandboxManager {
  async run(request: SandboxRequest): Promise<SandboxResult> {
    if (request.command.includes("\0")) throw new SandboxError("SANDBOX_POLICY_DENIED", "Sandbox command contains NUL")
    const policy = isolationPolicy(request.config)
    const input = await validateSandboxWorkspace(request.workspace, policy.maxInputBytes)
    const backend = policy.strictBackend === "auto" ? (process.platform === "win32" ? "wsl2" : "namespace") : policy.strictBackend
    if (backend === "wsl2") {
      if (process.platform !== "win32") throw new SandboxError("SANDBOX_UNAVAILABLE", "WSL2 backend requires Windows")
      return wslRun(request, policy, input.root, input.bytes)
    }
    return namespaceRun(request, policy, input.root, input.bytes)
  }
}

export const StrictSandbox = new SandboxManager()

