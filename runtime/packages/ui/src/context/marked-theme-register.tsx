import { registerCustomTheme } from "@pierre/diffs"
import { OpenCodeTheme } from "./marked-theme"

let registered = false

export function registerOpenCodeTheme() {
  if (registered) return
  registered = true
  registerCustomTheme("Base Harness", () => Promise.resolve(OpenCodeTheme))
}
