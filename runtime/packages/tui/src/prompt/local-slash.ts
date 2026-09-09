/** Match registered UI commands exactly, including multiword names and aliases. */
export function matchLocalSlash<Command extends { display: string; aliases?: readonly string[] }>(
  input: string,
  commands: readonly Command[],
): Command | undefined {
  const value = input.trim()
  if (!value.startsWith("/") || /[\r\n]/.test(value)) return
  return commands.find((command) =>
    command.display.trimEnd() === value || command.aliases?.some((alias) => alias === value),
  )
}

export type LocalSlashCommand = {
  display: string
  aliases?: readonly string[]
  /** One optional opaque token, validated by the command's authoritative owner. */
  argument?: string
}

export type LocalSlashResolution<Command> =
  | { kind: "command"; command: Command; arguments: readonly string[] }
  | { kind: "invalid"; usage: string }

export function resolveLocalSlash<Command extends LocalSlashCommand>(
  input: string,
  commands: readonly Command[],
): LocalSlashResolution<Command> | undefined {
  const value = input.trim()
  if (!value.startsWith("/")) return
  const exact = matchLocalSlash(value, commands)
  if (exact) return { kind: "command", command: exact, arguments: [] }

  // Multiword command names win over shorter names sharing their prefix.
  const match = commands.flatMap((command) =>
    [command.display.trimEnd(), ...(command.aliases ?? [])].map((name) => ({ command, name })),
  ).sort((a, b) => b.name.length - a.name.length)
    .find(({ name }) => value.startsWith(name) && /\s/.test(value[name.length] ?? ""))
  if (!match) return

  const { command, name } = match
  const usage = command.display.trimEnd() + (command.argument ? " [" + command.argument + "]" : "")
  const rest = value.slice(name.length).trim()
  const args = rest ? rest.split(/[ \t]+/) : []
  if (/[\r\n\x00-\x1f\x7f]/.test(value.replaceAll("\t", " ")) ||
      !command.argument || args.length !== 1) {
    return { kind: "invalid", usage }
  }
  return { kind: "command", command, arguments: args }
}
