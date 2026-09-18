import type { AutonomousRunPorts, CheckSpec, SubjectRef, VersionRef } from "@base-harness/domain-contracts"
import { ProcessMeasurementClient, type MeasurementCommandExecutor } from "@base-harness/verification"

export interface AutonomousMeasurementOptions {
  runId: string
  snapshotRoot: string
  environmentHash: string
  subject(ref: SubjectRef): { manifestJson: string }
  check(ref: VersionRef): CheckSpec
  executeCommand?: MeasurementCommandExecutor
}

/** The Coordinator owns the Python protocol; the app only supplies its normal
 * admitted execution adapter. The closure is owned by one Run's ports.
 */
export function createAutonomousMeasurementPorts(options: AutonomousMeasurementOptions): Pick<AutonomousRunPorts, "measure" | "authenticates" | "cleanup"> {
  let current: ProcessMeasurementClient | undefined
  let starting: Promise<ProcessMeasurementClient> | undefined
  const client = () => starting ??= ProcessMeasurementClient.start(options.runId, options.snapshotRoot, {
    executeCommand: options.executeCommand,
  }).then((value) => { current = value; return value })
  return {
    measure: async (proposal, signal) => {
      if (proposal.action.kind !== "measure" || proposal.basis.runId !== options.runId) throw new Error("AUTONOMOUS_MEASUREMENT_BINDING")
      signal.throwIfAborted()
      const { subject, checkRef } = proposal.action
      const stored = options.subject(subject)
      const check = options.check(checkRef)
      const process = await client()
      signal.throwIfAborted()
      return process.measure({ requestId: proposal.decisionId, runId: options.runId, taskId: proposal.basis.taskId,
        subject, manifestJson: stored.manifestJson, check, environmentHash: options.environmentHash }, signal)
    },
    authenticates: (report) => current?.authenticates(report) === true,
    cleanup: async () => {
      if (starting) {
        const pending = starting
        starting = undefined
        try { await (await pending).dispose() }
        finally { current = undefined }
      }
      return []
    },
  }
}
