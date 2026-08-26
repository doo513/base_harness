import { run as runTui, type TuiInput } from "@base-harness/tui"
import { Global } from "@base-harness/core/global"
import { AppNodeBuilder } from "@base-harness/core/effect/app-node-builder"
import { Effect } from "effect"

export function run(input: TuiInput) {
  return runTui(input).pipe(Effect.provide(AppNodeBuilder.build(Global.node)))
}
