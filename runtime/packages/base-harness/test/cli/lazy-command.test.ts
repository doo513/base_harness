import { describe, expect, test } from "bun:test"
import yargs from "yargs"
import type { Argv, CommandModule } from "yargs"
import { lazyCommand } from "../../src/cli/lazy-command"

describe("lazy command registration", () => {
  test("loads only the selected module and preserves options and global middleware", async () => {
    let selected = 0, unrelated = 0
    const handled: unknown[] = []
    const identity = { command:"run [message..]", describe:"run fixture" }
    const parser = yargs([]).exitProcess(false).strict()
      .middleware(args => { args.fromGlobal = true })
      .command(lazyCommand(identity, async () => {
        selected++
        return { ...identity, builder: argv => argv.option("effort", { choices:["high","max"],type:"string" }),
          handler: args => { handled.push({effort:args.effort,message:args.message,fromGlobal:args.fromGlobal}) } }
      }))
      .command(lazyCommand({command:"other",describe:"other fixture"}, async () => {
        unrelated++
        return {command:"other",describe:"other fixture",handler:() => {}}
      }))
    await parser.parseAsync(["run","hello","--effort","max"])
    expect(selected).toBe(1)
    expect(unrelated).toBe(0)
    expect(handled).toEqual([{effort:"max",message:["hello"],fromGlobal:true}])
  })

  test("help awaits the original builder without running the handler", async () => {
    let loaded = 0, handled = 0, output = ""
    const identity = {command:"run",describe:"run fixture"}
    const parser = yargs([]).exitProcess(false).help().command(lazyCommand(identity, async () => {
      loaded++
      return {...identity,builder: argv => argv.option("variant",{type:"string"}),handler:() => { handled++ }}
    }))
    await parser.parse(["run","--help"], (error: Error | undefined, _argv: unknown, text: string) => { if(error) throw error; output=text })
    expect(output).toContain("--variant")
    expect(loaded).toBe(1)
    expect(handled).toBe(0)
  })

  test.each(["--help", "-h", "--help=true"])("default help %s stays synchronous without loading the runtime", async (flag) => {
    let handled = 0, loaded = 0, output = ""
    const identity = { command: "$0 [project]", describe: "default fixture" }
    const builder = (argv: Argv) => argv.positional("project", { type: "string" }).option("mini", { type: "boolean" })
    const parser = yargs([]).exitProcess(false).help().alias("help", "h")
      .command(lazyCommand(identity, async () => {
        loaded++
        return { ...identity, builder, handler: () => { handled++ } }
      }, builder))
      .command({ command: "serve", describe: "server fixture", handler: () => {} })
    await parser.parse([flag], (error: Error | undefined, _argv: unknown, text: string) => {
      if (error) throw error
      output = text
    })
    expect(output).toContain("--mini")
    expect(output).toContain("serve")
    expect(loaded).toBe(0)
    expect(handled).toBe(0)
  })

  test("the synchronous builder preserves arguments when the lazy handler runs", async () => {
    let loaded = 0
    const handled: unknown[] = []
    const identity = { command: "$0 [project]", describe: "default fixture" }
    const builder = (argv: Argv) => argv.positional("project", { type: "string" }).option("mini", { type: "boolean" })
    const command = lazyCommand(identity, async () => {
      loaded++
      return { ...identity, builder, handler: args => { handled.push({ project: args.project, mini: args.mini }) } }
    }, builder)
    await yargs([]).exitProcess(false).command(command).parseAsync(["workspace", "--mini"])
    expect(loaded).toBe(1)
    expect(handled).toEqual([{ project: "workspace", mini: true }])
  })

  test("rejects a loaded builder that differs from the registered synchronous builder", async () => {
    let handled = false
    const identity = { command: "$0", describe: "default fixture" }
    const builder = (argv: Argv) => argv
    const command = lazyCommand(identity, async () => ({
      ...identity, builder: (argv: Argv) => argv, handler: () => { handled = true },
    }), builder)
    await expect(yargs([]).exitProcess(false).command(command).parseAsync([])).rejects.toThrow("CLI_COMMAND_BUILDER_MISMATCH")
    expect(handled).toBe(false)
  })

  test("supports declarative option builders and reuses the module promise", async () => {
    let loaded = 0
    const values: unknown[] = []
    const identity = {command:"count",describe:"count fixture",aliases:["c"]}
    const command = lazyCommand(identity, async () => {
      loaded++
      return {...identity,builder:{amount:{type:"number"}},handler:args => {values.push(args.amount)}}
    })
    await yargs([]).exitProcess(false).command(command).parseAsync(["c","--amount","2"])
    await yargs([]).exitProcess(false).command(command).parseAsync(["count","--amount","3"])
    expect(loaded).toBe(1)
    expect(values).toEqual([2,3])
  })

  test("rejects mismatched identity before executing a handler", async () => {
    let handled = false
    const command = lazyCommand({command:"safe",describe:"safe"}, async () => ({
      command:"different",describe:"safe",handler:() => {handled=true},
    }))
    await expect(yargs([]).exitProcess(false).command(command).parseAsync(["safe"])).rejects.toThrow("CLI_COMMAND_IDENTITY_MISMATCH")
    expect(handled).toBe(false)
  })

  test("propagates a module import failure without executing an alternative", async () => {
    const command = lazyCommand({command:"broken",describe:"broken"}, async () => {throw new Error("fixture import failure")})
    await expect(yargs([]).exitProcess(false).command(command).parseAsync(["broken"])).rejects.toThrow("fixture import failure")
  })

  test("rejects unsupported command middleware rather than dropping it", async () => {
    const identity = {command:"guarded",describe:"guarded"}
    const command = lazyCommand(identity, async () => ({...identity,middlewares:[() => {}],handler:() => {}} as CommandModule))
    await expect(yargs([]).exitProcess(false).command(command).parseAsync(["guarded"])).rejects.toThrow("CLI_LAZY_MIDDLEWARE_UNSUPPORTED")
  })

  test("root help advertises peripheral commands without loading their modules", async () => {
    let loaded = 0, output = ""
    const parser = yargs([]).exitProcess(false).help()
    for (const name of ["debug", "acp"]) {
      const identity = { command: name, describe: name + " fixture" }
      parser.command(lazyCommand(identity, async () => {
        loaded++
        return { ...identity, handler: () => {} }
      }))
    }
    await parser.parse(["--help"], (error: Error | undefined, _argv: unknown, text: string) => {
      if (error) throw error
      output = text
    })
    expect(output).toContain("debug")
    expect(output).toContain("acp")
    expect(loaded).toBe(0)
  })

  test("a selected lazy parent dispatches its nested command and preserves global options", async () => {
    let loaded = 0, parentHandled = 0
    const handled: unknown[] = []
    const identity = { command: "debug", describe: "debug fixture" }
    const parser = yargs([]).exitProcess(false).strict().option("pure", { type: "boolean" })
      .command(lazyCommand(identity, async () => {
        loaded++
        return {
          ...identity,
          builder: argv => argv.command({
            command: "paths",
            describe: "paths fixture",
            handler: args => { handled.push(args.pure) },
          }).demandCommand(),
          handler: () => { parentHandled++ },
        }
      }))
    await parser.parseAsync(["--pure", "debug", "paths"])
    expect(loaded).toBe(1)
    expect(handled).toEqual([true])
    expect(parentHandled).toBe(0)
  })

  test("nested help waits for a lazy parent without executing either handler", async () => {
    let loaded = 0, handled = 0, output = ""
    const identity = { command: "debug", describe: "debug fixture" }
    const parser = yargs([]).exitProcess(false).help().command(lazyCommand(identity, async () => {
      loaded++
      return {
        ...identity,
        builder: argv => argv.command({
          command: "paths",
          describe: "paths fixture",
          handler: () => { handled++ },
        }).demandCommand(),
        handler: () => { handled++ },
      }
    }))
    await parser.parse(["debug", "--help"], (error: Error | undefined, _argv: unknown, text: string) => {
      if (error) throw error
      output = text
    })
    expect(output).toContain("paths")
    expect(loaded).toBe(1)
    expect(handled).toBe(0)
  })

})
