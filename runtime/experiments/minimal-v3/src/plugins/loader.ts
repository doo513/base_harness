import { existsSync, realpathSync } from "node:fs"
import { pathToFileURL } from "node:url"
import type { ProviderRegistry } from "../providers/registry"
import type { ToolRegistry } from "../tools/registry"

export interface PluginContext { tools: ToolRegistry; providers: ProviderRegistry }
type PluginModule = { register?: (context: PluginContext) => void | Promise<void> }

export async function loadPlugins(paths: string[], context: PluginContext): Promise<void> {
  for (const path of paths) {
    if (!existsSync(path)) throw new Error(`Configured plugin does not exist: ${path}`)
    const url = pathToFileURL(realpathSync(path)).href
    const plugin = await import(url) as PluginModule
    if (typeof plugin.register !== "function") throw new Error(`Plugin must export register(context): ${path}`)
    await plugin.register(context)
  }
}
