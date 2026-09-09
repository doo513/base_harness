import path from "path"

export function abbreviateHome(input: string, home: string) {
  if (!home) return input
  // Attached Hosts can use a different path syntax from the TUI's local OS.
  const paths = (path.win32.isAbsolute(home) && !home.startsWith("/")) || home.startsWith("//")
    ? path.win32
    : home.startsWith("/") ? path.posix : path
  const relative = paths.relative(home, input)
  if (relative === "") return "~"
  if (relative === ".." || relative.startsWith(".." + paths.sep) || paths.isAbsolute(relative)) return input
  return "~" + paths.sep + relative
}
