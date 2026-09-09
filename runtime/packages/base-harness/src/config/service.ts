import { Context, type Effect } from "effect"
import type { ConfigV1 } from "@base-harness/core/v1/config/config"
import type { ConsoleState } from "@base-harness/core/v1/config/console-state"
import type { ConfigPlugin } from "./plugin"

// Service consumers depend on this contract, not configuration loading or auth.
export type Info = ConfigV1.Info & {
  plugin_origins?: ConfigPlugin.Origin[]
}

export interface Interface {
  readonly get: () => Effect.Effect<Info>
  readonly getGlobal: () => Effect.Effect<Info>
  readonly getConsoleState: () => Effect.Effect<ConsoleState>
  readonly update: (config: Info) => Effect.Effect<void>
  readonly updateGlobal: (config: Info) => Effect.Effect<{ info: Info; changed: boolean }>
  readonly invalidate: () => Effect.Effect<void>
  readonly directories: () => Effect.Effect<string[]>
  readonly waitForDependencies: () => Effect.Effect<void>
}

export class Service extends Context.Service<Service, Interface>()("@base-harness/Config") {}
