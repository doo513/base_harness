export type MeasurementStatus = "passed" | "failed" | "partial" | "not_run"

export interface EvidenceSummary {
  schemaVersion: "evidence-summary-v1"
  evidenceId: string
  runId: string
  scopeId: string
  actionId: string
  criterionId: string
  status: MeasurementStatus
  observed: Record<string, string | number | boolean | null>
  exitCode?: number | null
  artifact?: { path: string; sha256: string }
  detailRef?: string
  generatedAt: string
  truncated: boolean
}

export interface EvidenceSummaryInput {
  evidenceId: string
  runId: string
  scopeId: string
  actionId: string
  criterionId: string
  status: MeasurementStatus
  observed: Record<string, string | number | boolean | null>
  exitCode?: number | null
  artifact?: { path: string; sha256: string }
  detailRef?: string
  generatedAt?: string
  truncated?: boolean
}

/** Creates a compact measurement record; it is not an approval or Ready attestation. */
export function createEvidenceSummary(input: EvidenceSummaryInput): EvidenceSummary {
  for (const [name, value] of Object.entries(input)) {
    if (name === "exitCode" || name === "artifact" || name === "detailRef" || name === "generatedAt" || name === "truncated") continue
    if (typeof value === "string" && value.length === 0) throw new Error(`EVIDENCE_SUMMARY_${name.toUpperCase()}`)
  }
  if (!input.artifact && !input.detailRef && input.status !== "not_run") {
    throw new Error("EVIDENCE_SUMMARY_REFERENCE")
  }
  return {
    schemaVersion: "evidence-summary-v1",
    evidenceId: input.evidenceId,
    runId: input.runId,
    scopeId: input.scopeId,
    actionId: input.actionId,
    criterionId: input.criterionId,
    status: input.status,
    observed: { ...input.observed },
    exitCode: input.exitCode,
    artifact: input.artifact ? { ...input.artifact } : undefined,
    detailRef: input.detailRef,
    generatedAt: input.generatedAt ?? new Date().toISOString(),
    truncated: input.truncated ?? false,
  }
}

/** One-line JSON is deliberately small enough for an LLM to inspect without raw logs. */
export function serializeEvidenceSummary(summary: EvidenceSummary): string {
  return `${JSON.stringify(summary)}\n`
}
