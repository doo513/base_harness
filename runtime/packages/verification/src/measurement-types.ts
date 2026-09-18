import type { CheckSpec, ObservationReport, SubjectRef } from "@base-harness/domain-contracts"

export const MEASUREMENT_PROTOCOL_VERSION = 5 as const

/** Host-created immutable manifest. sha256(manifestJson UTF-8) equals subject.sha256. */
export interface MeasurementManifest {
  kind: SubjectRef["kind"]
  files: Array<{ path: string; sha256: string; size: number }>
  /** Relevant input/baseline identities, including those outside the measured files. */
  dependencies: SubjectRef[]
}

export interface MeasurementRequest {
  requestId: string
  runId: string
  taskId: string
  subject: SubjectRef
  manifestJson: string
  check: CheckSpec
  environmentHash: string
}

/** Returned only by the registered execution adapter, never accepted from model JSON. */
export type ProcessCapture = {
  argv: string[]
  cwd: string
  startedAt: string
  finishedAt: string
  stdout: string
  stderr: string
} & (
  | { execution: "completed"; exitCode: number }
  | { execution: "not_run"; reason: string }
  | { execution: "error"; error: { code: string; message: string } }
)

export interface MeasurementClient {
  readonly runId: string
  measure(request: MeasurementRequest, signal: AbortSignal): Promise<ObservationReport>
  authenticates(report: ObservationReport): boolean
  dispose(): Promise<void>
}

/** Installed by app composition; implementation must use normal permission/sandbox gates. */
export type MeasurementCommandExecutor = (request: Readonly<MeasurementRequest>, signal: AbortSignal) => Promise<ProcessCapture>
