export const STARTUP_TRACE_PREFIX = "[base-harness.startup] "
export const PROVIDER_STARTUP_STAGES = [
  "provider.services_start",
  "provider.services_ready",
  "provider.init_start",
  "provider.bridge_ready",
  "provider.config_ready",
  "provider.catalog_ready",
  "provider.catalog_mapped",
  "provider.plugins_ready",
  "provider.plugin_models_ready",
  "provider.config_models_ready",
  "provider.env_ready",
  "provider.credentials_ready",
  "provider.plugin_auth_ready",
  "provider.custom_loaders_ready",
  "provider.init_ready",
] as const
export const ACP_STARTUP_STAGES = [
  "acp.config_import_start",
  "acp.config_import_ready",
  "acp.runtime_imports_start",
  "acp.runtime_imports_ready",
  "acp.services_start",
  "acp.services_ready",
  "acp.server_import_start",
  "acp.server_import_ready",
  "acp.agent_import_start",
  "acp.agent_import_ready",
  "acp.config_read_start",
  "acp.config_read_ready",
  "acp.listen_start",
  "acp.listen_ready",
  "acp.connection_ready",
] as const
export const STARTUP_STAGES = [
  ...ACP_STARTUP_STAGES,
  ...PROVIDER_STARTUP_STAGES,
  "launcher.start", "launcher.workspace_ready", "launcher.import_start", "launcher.import_failed",
"cli.modules_ready", "cli.parse_start", "cli.options_ready", "cli.failed", "cli.exiting",
  "cli.input_wait", "cli.input_ready", "cli.input_eof",
"runtime.import_start", "runtime.import_ready", "runtime.services_start",
  "runtime.modules_ready", "runtime.layer_ready", "runtime.managed_ready",
  "host.handler_start", "host.module_ready", "host.options_ready", "host.listen_start", "host.listen_ready",
] as const
export type StartupStage = typeof STARTUP_STAGES[number]

export interface StartupTraceOptions {
  enabled: () => boolean
  write: (line: string) => unknown
  now: () => number
  uptimeMs: () => number
  pid: () => number
  pureRequested: () => boolean
}

/** Diagnostic only: never an Action, FailureEnvelope, Evidence or Ready producer. */
export function createStartupTrace(options: StartupTraceOptions) {
  const startedAt = options.now()
  let sequence = 0
  return (stage: StartupStage): void => {
    try {
      if (!options.enabled() || !STARTUP_STAGES.includes(stage) || sequence >= 32) return
      const event = {
        version: 1,
        type: "harness.startup",
        stage,
        sequence: ++sequence,
        elapsedMs: Math.max(0, Math.round(options.now() - startedAt)),
        processUptimeMs: Math.max(0, Math.round(options.uptimeMs())),
        pid: options.pid(),
        pureRequested: options.pureRequested(),
      }
      options.write(STARTUP_TRACE_PREFIX + JSON.stringify(event) + "\n")
    } catch {
      // An optional synchronous diagnostic sink failure must not alter startup.
    }
  }
}

export const traceStartup = createStartupTrace({
  enabled: () => process.env.BASE_HARNESS_TRACE_STARTUP === "1",
  write: (line) => { process.stderr.write(line) },
  now: () => performance.now(),
  uptimeMs: () => process.uptime() * 1000,
  pid: () => process.pid,
  pureRequested: () => process.env.BASE_HARNESS_PURE === "1",
})
