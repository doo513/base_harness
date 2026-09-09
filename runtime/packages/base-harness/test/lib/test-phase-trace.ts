const enabled = () => process.env.BASE_HARNESS_TRACE_TEST_PHASES === "1"
let sequence = 0

/** Bounded developer diagnostics. Never records commands, paths or credentials. */
export function traceTestPhase(phase: string) {
  if (!enabled() || sequence >= 128) return
  try {
    process.stderr.write("TEST_PHASE_DIAGNOSTIC " + JSON.stringify({
      diagnosticOnly: true,
      notHarnessEvidence: true,
      notIndependentUserValidation: true,
      sequence: ++sequence,
      phase,
      processUptimeMs: Math.round(process.uptime() * 1000),
    }) + "\n")
  } catch {
    // Optional diagnostics must not affect fixture behavior.
  }
}

