import { Effect, Layer } from "effect"
import { cmd } from "./cmd"
import { EntryCommand } from "../entry-command-metadata"
import { AgentSideConnection, ndJsonStream } from "@agentclientprotocol/sdk"
import { ServerAuth } from "@/server/auth"
import { createOpencodeClient } from "@base-harness/sdk/v2"
import { withNetworkOptions, resolveNetworkOptions, type NetworkOptions } from "../network"
import { ACPProfile } from "@/acp/profile"
import { waitForAcpInput } from "../acp-input"
import { traceStartup } from "@/util/startup-trace"

const acpHandler = Effect.fn("Cli.acp")(function* (args: NetworkOptions) {
    traceStartup("acp.services_ready")
    traceStartup("acp.server_import_start")
    const { Server } = yield* Effect.promise(() => import("@/server/server"))
    traceStartup("acp.server_import_ready")
    traceStartup("acp.agent_import_start")
    const { ACP } = yield* Effect.promise(() => import("@/acp/agent"))
    traceStartup("acp.agent_import_ready")
    ACPProfile.mark("cli.acp.handler")
    process.env.BASE_HARNESS_CLIENT = "acp"
    traceStartup("acp.config_read_start")
    const opts = yield* resolveNetworkOptions(args)
    traceStartup("acp.config_read_ready")
    traceStartup("acp.listen_start")
    yield* Effect.acquireUseRelease(
      Effect.promise(() => ACPProfile.measure("cli.acp.server.listen", () => Server.listen(opts))),
      (server) => Effect.gen(function* () {
    traceStartup("acp.listen_ready")

    const sdk = createOpencodeClient({
      baseUrl: `http://${server.hostname}:${server.port}`,
      headers: ServerAuth.headers(),
    })

    const input = new WritableStream<Uint8Array>({
      write(chunk) {
        return new Promise<void>((resolve, reject) => {
          process.stdout.write(chunk, (err) => {
            if (err) {
              reject(err)
            } else {
              resolve()
            }
          })
        })
      },
    })
    let finish!: () => void
    let fail!: (error: Error) => void
    const ended = new Promise<void>((resolve, reject) => {
      finish = resolve
      fail = reject
    })
    // Observe EOF in the stream handler itself, before any asynchronous setup.
    // Attaching another end listener after setup can miss an already delivered EOF.
    void ended.catch(() => {})
    const output = new ReadableStream<Uint8Array>({
      start(controller) {
        if (process.stdin.readableEnded) {
          controller.close()
          finish()
          return
        }
        process.stdin.on("data", (chunk: Buffer) => {
          controller.enqueue(new Uint8Array(chunk))
        })
        process.stdin.once("end", () => {
          controller.close()
          finish()
        })
        process.stdin.once("error", (err) => {
          controller.error(err)
          fail(err)
        })
      },
    })

    const stream = ndJsonStream(input, output)
    const agent = ACP.init({ sdk })

    yield* Effect.gen(function* () {
      new AgentSideConnection((conn) => {
        ACPProfile.mark("cli.acp.connection.create")
        return agent.create(conn)
      }, stream)
      traceStartup("acp.connection_ready")

      yield* Effect.logInfo("setup connection")
      process.stdin.resume()
      yield* Effect.promise(() => ended)
    }).pipe(Effect.ensuring(Effect.sync(() => agent.dispose())))
      }),
      (server) => Effect.promise(() => server.stop(true)),
    )
})

const runtimeAcpCommand = cmd({
  ...EntryCommand.acp,
  builder: (yargs) => {
    return withNetworkOptions(yargs).option("cwd", {
      describe: "working directory",
      type: "string",
      default: process.cwd(),
    })
  },
  async handler(args) {
    // The Host server owns its execution runtime. This transport only needs
    // global configuration; do not acquire the entire agent runtime twice.
    traceStartup("acp.config_import_start")
    const { Config } = await import("@/config/config")
    traceStartup("acp.config_import_ready")
    traceStartup("acp.runtime_imports_start")
    const { AppNodeBuilder } = await import("@base-harness/core/effect/app-node-builder")
    const Observability = await import("@base-harness/core/observability")
    traceStartup("acp.runtime_imports_ready")
    traceStartup("acp.services_start")
    await Effect.runPromise(
      acpHandler(args).pipe(
        Effect.provide(Layer.mergeAll(AppNodeBuilder.build(Config.node), Observability.layer)),
        Effect.scoped,
      ),
    )
  },
})

// An empty, closed transport must return before acquiring configuration or Host services.
export const AcpCommand: typeof runtimeAcpCommand = {
  ...runtimeAcpCommand,
  async handler(args) {
    traceStartup("cli.input_wait")
    const hasInput = await waitForAcpInput(process.stdin)
    traceStartup(hasInput ? "cli.input_ready" : "cli.input_eof")
    if (!hasInput) return
    await runtimeAcpCommand.handler(args)
  },
}
