import type { Argv, CommandModule } from "yargs"

type AnyCommand = CommandModule<any, any>
type SynchronousBuilder = (argv: Argv<any>, helpOrVersion?: boolean) => Argv<any>
type Identity = Pick<AnyCommand, "describe" | "aliases" | "deprecated"> & { command: string }

/** Named commands may load their builders lazily; root help needs a synchronous builder. */
export function lazyCommand(identity: Identity, load: () => Promise<AnyCommand>, registeredBuilder?: SynchronousBuilder): AnyCommand {
  let pending: Promise<AnyCommand> | undefined
  const resolve = () => pending ??= Promise.resolve().then(load).then(command => {
    if (command.command !== identity.command || command.describe !== identity.describe ||
        JSON.stringify(command.aliases ?? []) !== JSON.stringify(identity.aliases ?? []) ||
        command.deprecated !== identity.deprecated) {
      throw new Error("CLI_COMMAND_IDENTITY_MISMATCH")
    }
    // yargs registers command middleware before invoking its builder. Never silently
    // drop such middleware when a future command is moved behind this adapter.
    const middleware = (command as AnyCommand & { middlewares?: readonly unknown[] }).middlewares
    if (middleware?.length) throw new Error("CLI_LAZY_MIDDLEWARE_UNSUPPORTED")
    if (registeredBuilder && command.builder !== registeredBuilder) throw new Error("CLI_COMMAND_BUILDER_MISMATCH")
    return command
  })

  const builder = async (argv: Argv, helpOrVersion?: boolean) => {
    const command = await resolve()
    if (typeof command.builder === "function") {
      // The installed runtime accepts a promise; some yargs declaration versions
      // describe only synchronous builders. Keep that compatibility cast here.
      const build = command.builder as (argv: Argv, helpOrVersion?: boolean) => Argv | void | Promise<Argv | void>
      return await build(argv, helpOrVersion) ?? argv
    }
    return command.builder ? argv.options(command.builder) : argv
  }

  return {
    ...identity,
    builder: registeredBuilder ?? (builder as unknown as AnyCommand["builder"]),
    handler: async (args) => { await (await resolve()).handler?.(args) },
  }
}
