import { GlobalSecretRegistryHub, type SecretFinding } from "@base-harness/security/secret-registry"

export class PersistenceGateway {
  openRun(runId: string) {
    GlobalSecretRegistryHub.openRun(runId)
  }

  closeRun(runId: string) {
    GlobalSecretRegistryHub.closeRun(runId)
  }

  redact<T>(runId: string, value: T): T {
    return GlobalSecretRegistryHub.redact(runId, value) as T
  }

  findings(runId: string, value: unknown): SecretFinding[] {
    return GlobalSecretRegistryHub.findings(runId, value)
  }
}
