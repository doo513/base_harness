import { STARTUP_STAGES, STARTUP_TRACE_PREFIX, type StartupStage } from "../../src/util/startup-trace"
import { freemem, totalmem } from "node:os"

export interface AcpResources {
  parentRssBytes: number
  parentHeapUsedBytes: number
  systemFreeBytes: number
  systemTotalBytes: number
}

/** Only numeric resource counters are projected; optional sampling cannot fail a test. */
export function captureAcpResources(read: () => AcpResources = () => {
  const memory = process.memoryUsage()
  return {
    parentRssBytes: memory.rss,
    parentHeapUsedBytes: memory.heapUsed,
    systemFreeBytes: freemem(),
    systemTotalBytes: totalmem(),
  }
}): AcpResources | undefined {
  try {
    const value = read()
    const result = {
      parentRssBytes: value.parentRssBytes,
      parentHeapUsedBytes: value.parentHeapUsedBytes,
      systemFreeBytes: value.systemFreeBytes,
      systemTotalBytes: value.systemTotalBytes,
    }
    if (!Object.values(result).every((n) => Number.isSafeInteger(n) && n >= 0)) return
    return result
  } catch {
    return undefined
  }
}

export interface AcpDiagnostics {
  pid: number
  elapsedMs: number
  exitCode: number | null
  stdoutLines: number
  startup: Array<{ stage: StartupStage; processUptimeMs: number }>
  resources?: { atSpawn?: AcpResources; atObservation?: AcpResources }
}

// Diagnostic only. Never include raw stderr, provider payloads, or credentials.
export function summarizeAcpStartup(stderr: string): AcpDiagnostics["startup"] {
  const stages: AcpDiagnostics["startup"] = []
  for (const line of stderr.slice(-8192).split("\n")) {
    if (!line.startsWith(STARTUP_TRACE_PREFIX)) continue
    try {
      const value = JSON.parse(line.slice(STARTUP_TRACE_PREFIX.length))
      if (
        value?.version !== 1 ||
        value?.type !== "harness.startup" ||
        !STARTUP_STAGES.includes(value.stage) ||
        typeof value.processUptimeMs !== "number" ||
        !Number.isFinite(value.processUptimeMs) ||
        value.processUptimeMs < 0
      ) continue
      stages.push({ stage: value.stage, processUptimeMs: value.processUptimeMs })
    } catch {
      // Partial or malformed diagnostic lines are not protocol failures.
    }
  }
  return stages.slice(-32)
}

export function acpTimeoutError(handle: { diagnostics?: () => AcpDiagnostics }, operation: string): Error {
  return new Error("ACP_TIMEOUT: " + operation + " " + JSON.stringify(handle.diagnostics?.() ?? { unavailable: true }))
}
