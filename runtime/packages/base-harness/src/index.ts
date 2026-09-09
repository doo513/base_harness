process.env.BASE_HARNESS_DISABLE_AUTOUPDATE ??= "1"
import "./plugin/builtin-module"
import yargs from "yargs"
import { hideBin } from "yargs/helpers"
import { GenerateCommand } from "./cli/cmd/generate"




import { UI } from "./cli/ui"
import { InstallationVersion } from "@base-harness/core/installation/version"
import { FormatError } from "./cli/error"





import { EOL } from "os"



import { errorMessage } from "./util/error"

import { Heap } from "./cli/heap"
import { traceStartup } from "./util/startup-trace"
import { EntryCommand } from "./cli/entry-command-metadata"
import { lazyCommand } from "./cli/lazy-command"
import { TuiCommandBuilder } from "./cli/tui-options"

const ConsoleCommand = lazyCommand(EntryCommand.console, () => import("./cli/cmd/account").then(module => module.ConsoleCommand))
const AgentCommand = lazyCommand(EntryCommand.agent, () => import("./cli/cmd/agent").then(module => module.AgentCommand))
const ModelsCommand = lazyCommand(EntryCommand.models, () => import("./cli/cmd/models").then(module => module.ModelsCommand))
const StatsCommand = lazyCommand(EntryCommand.stats, () => import("./cli/cmd/stats").then(module => module.StatsCommand))
const ExportCommand = lazyCommand(EntryCommand.export, () => import("./cli/cmd/export").then(module => module.ExportCommand))
const ImportCommand = lazyCommand(EntryCommand.import, () => import("./cli/cmd/import").then(module => module.ImportCommand))
const SessionCommand = lazyCommand(EntryCommand.session, () => import("./cli/cmd/session").then(module => module.SessionCommand))
const PluginCommand = lazyCommand(EntryCommand.plugin, () => import("./cli/cmd/plug").then(module => module.PluginCommand))
const DbCommand = lazyCommand(EntryCommand.db, () => import("./cli/cmd/db").then(module => module.DbCommand))
const ServeCommand = lazyCommand(EntryCommand.serve, () => import("./cli/cmd/serve").then(module => module.ServeCommand))
const WebCommand = lazyCommand(EntryCommand.web, () => import("./cli/cmd/web").then(module => module.WebCommand))
const ProvidersCommand = lazyCommand(EntryCommand.providers, () => import("./cli/cmd/providers").then(module => module.ProvidersCommand))
const McpCommand = lazyCommand(EntryCommand.mcp, () => import("./cli/cmd/mcp").then(module => module.McpCommand))

const DebugCommand = lazyCommand(EntryCommand.debug, () => import("./cli/cmd/debug").then(module => module.DebugCommand))
const AcpCommand = lazyCommand(EntryCommand.acp, () => import("./cli/cmd/acp").then(module => module.AcpCommand))

const RunCommand = lazyCommand(EntryCommand.run, () => import("./cli/cmd/run").then(module => module.RunCommand))
const ExecuteCommand = lazyCommand(EntryCommand.execute, () => import("./cli/cmd/run").then(module => module.ExecuteCommand))
const AttachCommand = lazyCommand(EntryCommand.attach, () => import("./cli/cmd/attach").then(module => module.AttachCommand))
const TuiThreadCommand = lazyCommand(EntryCommand.tui, () => import("./cli/cmd/tui").then(module => module.TuiThreadCommand), TuiCommandBuilder)

traceStartup("cli.modules_ready")
const args = hideBin(process.argv)

function show(out: string) {
  const text = out.trimStart()
  if (!text.startsWith("base-harness ")) {
    process.stderr.write(UI.logo() + EOL + EOL)
    process.stderr.write(text + EOL)
    return
  }
  process.stderr.write(out)
}

const cli = yargs(args)
  .parserConfiguration({ "populate--": true })
  .scriptName("base-harness")
  .wrap(100)
  .help("help", "show help")
  .alias("help", "h")
  .version("version", "show version number", InstallationVersion)
  .alias("version", "v")
  .option("print-logs", {
    describe: "print logs to stderr",
    type: "boolean",
  })
  .option("log-level", {
    describe: "log level",
    type: "string",
    choices: ["DEBUG", "INFO", "WARN", "ERROR"],
  })
  .option("pure", {
    describe: "run without external plugins",
    type: "boolean",
  })
  .middleware(async (opts) => {
    if (opts.printLogs) process.env.BASE_HARNESS_PRINT_LOGS = "1"
    if (opts.logLevel) process.env.BASE_HARNESS_LOG_LEVEL = opts.logLevel
    if (opts.pure) {
      process.env.BASE_HARNESS_PURE = "1"
    }

    traceStartup("cli.options_ready")
    Heap.start()

    process.env.AGENT = "1"
    process.env.BASE_HARNESS_PID = String(process.pid)
  })
  .usage("")
  .completion("completion", "generate shell completion script")
  .command(AcpCommand)
  .command(McpCommand)
  .command(TuiThreadCommand)
  .command(AttachCommand)
  .command(RunCommand)
  .command(ExecuteCommand)
  .command(GenerateCommand)
  .command(DebugCommand)
  .command(ConsoleCommand)
  .command(ProvidersCommand)
  .command(AgentCommand)
  .command(ServeCommand)
  .command(WebCommand)
  .command(ModelsCommand)
  .command(StatsCommand)
  .command(ExportCommand)
  .command(ImportCommand)
  .command(SessionCommand)
  .command(PluginCommand)
  .command(DbCommand)
  .fail((msg, err) => {
    if (
      msg?.startsWith("Unknown argument") ||
      msg?.startsWith("Not enough non-option arguments") ||
      msg?.startsWith("Invalid values:")
    ) {
      if (err) throw err
      cli.showHelp(show)
    }
    if (err) throw err
    process.exit(1)
  })
  .strict()

try {
  traceStartup("cli.parse_start")
  if (args.includes("-h") || args.includes("--help")) {
    await cli.parse(args, (err: Error | undefined, _argv: unknown, out: string) => {
      if (err) throw err
      if (!out) return
      show(out)
    })
  } else {
    await cli.parse()
  }
} catch (e) {
  traceStartup("cli.failed")
  const formatted = FormatError(e)
  if (formatted) UI.error(formatted)
  if (formatted === undefined) {
    UI.error("Unexpected error" + EOL)
    process.stderr.write(errorMessage(e) + EOL)
  }
  process.exitCode = 1
} finally {
  traceStartup("cli.exiting")
  // Some subprocesses don't react properly to SIGTERM and similar signals.
  // Most notably, some docker-container-based MCP servers don't handle such signals unless
  // run using `docker run --init`.
  // Explicitly exit to avoid any hanging subprocesses.
  process.exit()
}
