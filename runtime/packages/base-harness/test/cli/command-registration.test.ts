import { describe, expect, test } from "bun:test"
import { EntryCommand } from "../../src/cli/entry-command-metadata"

describe("CLI command registration boundary", () => {
  test("defers named command implementations instead of importing them at entry", async () => {
    const source = await Bun.file(new URL("../../src/index.ts", import.meta.url)).text()
    const imports = new Bun.Transpiler({ loader: "ts" }).scanImports(source)
    const commands = imports.filter((entry) => entry.path.startsWith("./cli/cmd/"))
    // The tiny hidden generator already defers its implementation imports.
    expect(commands.filter((entry) => entry.kind === "import-statement").map((entry) => entry.path))
      .toEqual(["./cli/cmd/generate"])
    const deferred = commands.filter((entry) => entry.kind === "dynamic-import").map((entry) => entry.path)
    for (const name of ["account", "agent", "models", "stats", "export", "import", "session", "plug", "db",
      "serve", "web", "providers", "mcp", "acp", "run", "attach", "tui", "debug"]) {
      expect(deferred).toContain("./cli/cmd/" + name)
    }
  })

  test("keeps command identities, hidden commands, and aliases unambiguous", () => {
    const names = Object.values(EntryCommand).flatMap((entry) => [
      entry.command.split(" ")[0],
      ...("aliases" in entry ? entry.aliases : []),
    ])
    expect(new Set(names).size).toBe(names.length)
    expect(EntryCommand.console.describe).toBe(false)
    expect(EntryCommand.providers.aliases).toEqual(["auth"])
    expect(EntryCommand.plugin.aliases).toEqual(["plug"])
  })
})
