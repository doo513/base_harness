import { EntryCommand } from "../entry-command-metadata"
import { Effect } from "effect"
import { effectCmd } from "../effect-cmd"
import { withNetworkOptions, resolveNetworkOptions } from "../network"
import { Flag } from "@base-harness/core/flag/flag"
import { traceStartup } from "../../util/startup-trace"

export const ServeCommand = effectCmd({
  ...EntryCommand.serve,
  builder: (yargs) => withNetworkOptions(yargs),
  // Server loads instances per-request via x-base-harness-directory header — no
  // need for an ambient project InstanceContext at startup.
  instance: false,
  handler: Effect.fn("Cli.serve")(function* (args) {
    traceStartup("host.handler_start")
    const { Server } = yield* Effect.promise(() => import("../../server/server"))
    traceStartup("host.module_ready")
    if (!Flag.BASE_HARNESS_SERVER_PASSWORD) {
      console.log("Warning: BASE_HARNESS_SERVER_PASSWORD is not set; server is unsecured.")
    }
    const opts = yield* resolveNetworkOptions(args)
    traceStartup("host.options_ready")
    traceStartup("host.listen_start")
    const server = yield* Effect.promise(() => Server.listen(opts))
    traceStartup("host.listen_ready")
    console.log(`base-harness server listening on http://${server.hostname}:${server.port}`)
    yield* Effect.never
  }),
})
