import { describe, expect, test } from "bun:test"
import { createStartupTrace, PROVIDER_STARTUP_STAGES, STARTUP_TRACE_PREFIX, type StartupStage, type StartupTraceOptions } from "../../src/util/startup-trace"

function fixture(overrides: Partial<StartupTraceOptions> = {}) {
  const lines: string[] = []
  let now = 100
  const trace = createStartupTrace({
    enabled: () => true,
    write: line => lines.push(line),
    now: () => now,
    uptimeMs: () => 1234,
    pid: () => 77,
    pureRequested: () => true,
    ...overrides,
  })
  return { lines, trace, advance(value: number) { now += value } }
}

describe("bounded secret-free startup trace", () => {
  test("disabled tracing does not emit or collect optional metadata", () => {
    const f = fixture({ enabled: () => false, pureRequested: () => { throw new Error("must not collect") } })
    f.trace("launcher.start")
    expect(f.lines).toEqual([])
  })

  test("emits only the fixed schema and monotonic elapsed measurement", () => {
    const f = fixture()
    f.advance(15)
    f.trace("host.listen_ready")
    expect(f.lines).toHaveLength(1)
    const event = JSON.parse(f.lines[0].slice(STARTUP_TRACE_PREFIX.length))
    expect(event).toEqual({
      version: 1, type: "harness.startup", stage: "host.listen_ready", sequence: 1,
      elapsedMs: 15, processUptimeMs: 1234, pid: 77, pureRequested: true,
    })
  })

  test("rejects runtime labels containing arbitrary input", () => {
    const f = fixture()
    f.trace("secret=/workspace/private-prompt" as StartupStage)
    f.trace("launcher.start")
    expect(f.lines).toHaveLength(1)
    expect(f.lines[0]).not.toContain("secret")
    expect(f.lines[0]).not.toContain("workspace")
    expect(JSON.parse(f.lines[0].slice(STARTUP_TRACE_PREFIX.length)).sequence).toBe(1)
  })

  test("caps output at 32 events", () => {
    const f = fixture()
    for (let i = 0; i < 50; i++) f.trace("runtime.services_start")
    expect(f.lines).toHaveLength(32)
    expect(JSON.parse(f.lines[31].slice(STARTUP_TRACE_PREFIX.length)).sequence).toBe(32)
  })

  test("contains synchronous sink failures", () => {
    const f = fixture({ write: () => { throw new Error("closed diagnostic sink") } })
    expect(() => f.trace("launcher.start")).not.toThrow()
  })
})

test("provider diagnostics use the same bounded schema without identity or credential fields", () => {
  const f = fixture()
  for (const stage of PROVIDER_STARTUP_STAGES) {
    f.advance(1)
    f.trace(stage)
  }
  const events = f.lines.map(line => JSON.parse(line.slice(STARTUP_TRACE_PREFIX.length)))
  expect(events.map(event => event.stage)).toEqual([...PROVIDER_STARTUP_STAGES])
  for (const event of events) {
    expect(Object.keys(event).sort()).toEqual([
      "elapsedMs", "pid", "processUptimeMs", "pureRequested", "sequence", "stage", "type", "version",
    ])
  }
  const disabled = fixture({ enabled: () => false })
  for (const stage of PROVIDER_STARTUP_STAGES) disabled.trace(stage)
  expect(disabled.lines).toEqual([])
})
