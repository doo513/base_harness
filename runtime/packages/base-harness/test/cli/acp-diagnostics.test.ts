import { describe, expect, test } from "bun:test"
import { acpTimeoutError, captureAcpResources, summarizeAcpStartup } from "../lib/acp-diagnostics"
import { ACP_STARTUP_STAGES, STARTUP_TRACE_PREFIX } from "../../src/util/startup-trace"

function trace(extra: Record<string, unknown> = {}) {
  return STARTUP_TRACE_PREFIX + JSON.stringify({
    version: 1, type: "harness.startup", stage: "cli.modules_ready", processUptimeMs: 12, ...extra,
  }) + "\n"
}

describe("ACP bounded startup diagnostics", () => {
  test("retains ACP bootstrap boundaries without arbitrary payloads", () => {
    const result = summarizeAcpStartup(ACP_STARTUP_STAGES.map((stage, index) =>
      trace({ stage, processUptimeMs: index, credential: "do-not-persist" }),
    ).join(""))
    expect(result).toEqual(ACP_STARTUP_STAGES.map((stage, index) => ({ stage, processUptimeMs: index })))
    expect(JSON.stringify(result)).not.toContain("do-not-persist")
  })

  test("projects only numeric resource counters", () => {
    const raw = { parentRssBytes: 1024, parentHeapUsedBytes: 512, systemFreeBytes: 4096, systemTotalBytes: 8192, token: "secret" }
    expect(captureAcpResources(() => raw)).toEqual({
      parentRssBytes: 1024, parentHeapUsedBytes: 512, systemFreeBytes: 4096, systemTotalBytes: 8192,
    })
    expect(JSON.stringify(captureAcpResources(() => raw))).not.toContain("secret")
  })

  test("sampling errors and invalid counters remain optional", () => {
    expect(captureAcpResources(() => { throw new Error("unavailable") })).toBeUndefined()
    for (const invalid of [-1, NaN, Infinity, 0.5, Number.MAX_SAFE_INTEGER + 1]) {
      expect(captureAcpResources(() => ({
        parentRssBytes: invalid, parentHeapUsedBytes: 0, systemFreeBytes: 1, systemTotalBytes: 2,
      }))).toBeUndefined()
    }
  })

  test("includes spawn and observation resources without requiring them on old handles", () => {
    const sample = { parentRssBytes: 1024, parentHeapUsedBytes: 512, systemFreeBytes: 4096, systemTotalBytes: 8192 }
    const error = acpTimeoutError({ diagnostics: () => ({
      pid: 42, elapsedMs: 15000, exitCode: null, stdoutLines: 0, startup: [],
      resources: { atSpawn: sample, atObservation: sample },
    }) }, "request:initialize")
    expect(error.message).toContain('"atSpawn"')
    expect(error.message).toContain('"atObservation"')
    expect(error.message).toContain('"parentRssBytes":1024')
  })

  test("projects only declared stages and timing, never raw payloads", () => {
    const result = summarizeAcpStartup(
      "secret-raw-stderr\n" + trace({ token: "secret-token" }) +
      trace({ stage: "untrusted-stage" }) + trace({ processUptimeMs: -1 }) +
      STARTUP_TRACE_PREFIX + "{broken\n",
    )
    expect(result).toEqual([{ stage: "cli.modules_ready", processUptimeMs: 12 }])
    expect(JSON.stringify(result)).not.toContain("secret")
  })

  test("bounds diagnostic history and ignores old data outside the tail", () => {
    expect(summarizeAcpStartup(trace() + "x".repeat(8193))).toEqual([])
    const result = summarizeAcpStartup(Array.from({ length: 80 }, (_, i) => trace({ processUptimeMs: i })).join(""))
    expect(result).toHaveLength(32)
    expect(result.at(-1)?.processUptimeMs).toBe(79)
  })

  test("identifies the operation and child state on timeout", () => {
    const error = acpTimeoutError({ diagnostics: () => ({
      pid: 42, elapsedMs: 5000, exitCode: null, stdoutLines: 0,
      startup: [{ stage: "cli.parse_start", processUptimeMs: 40 }],
    }) }, "stdin_eof")
    expect(error.message).toContain("ACP_TIMEOUT: stdin_eof")
    expect(error.message).toContain('"pid":42')
    expect(error.message).toContain("cli.parse_start")
  })

  test("supports older test doubles without diagnostics", () => {
    expect(acpTimeoutError({}, "initialize").message).toContain('"unavailable":true')
  })
})
