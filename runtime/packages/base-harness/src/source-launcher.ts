import { traceStartup } from "./util/startup-trace"

traceStartup("launcher.start")
const workspace = process.env.BASE_HARNESS_LAUNCH_CWD

if (!workspace) {
  throw new Error("BASE_HARNESS_LAUNCH_CWD is required by the source installation launcher")
}

process.chdir(workspace)
traceStartup("launcher.workspace_ready")
traceStartup("launcher.import_start")
try {
  await import("./index")
} catch (error) {
  traceStartup("launcher.import_failed")
  throw error
}
