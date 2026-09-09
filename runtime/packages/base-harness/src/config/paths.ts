export * as ConfigPaths from "./paths"

import path from "path"
import { Flag } from "@base-harness/core/flag/flag"
import { Global } from "@base-harness/core/global"
import { unique } from "remeda"
import * as Effect from "effect/Effect"
import { FSUtil } from "@base-harness/core/fs-util"

export const files = Effect.fn("ConfigPaths.projectFiles")(function* (
  name: string,
  directory: string,
  worktree?: string,
) {
  const afs = yield* FSUtil.Service
  return (yield* afs.up({
    // up() walks nearest-first and the result is reversed below. Search JSONC
    // first so it is applied after JSON within each directory. Only TUI accepts
    // both formats; server project configuration remains JSONC-only.
    targets: name === "tui" ? ["tui.jsonc", "tui.json"] : [`${name}.jsonc`],
    start: directory,
    stop: worktree,
  })).toReversed()
})

export const directories = Effect.fn("ConfigPaths.directories")(function* (directory: string, worktree?: string) {
  const afs = yield* FSUtil.Service
  return unique([
    Global.Path.config,
    ...(!Flag.BASE_HARNESS_DISABLE_PROJECT_CONFIG
      ? yield* afs.up({
          targets: [".base-harness"],
          start: directory,
          stop: worktree,
        })
      : []),
    ...(yield* afs.up({
      targets: [".base-harness"],
      start: Global.Path.home,
      stop: Global.Path.home,
    })),
    ...(Flag.BASE_HARNESS_CONFIG_DIR ? [Flag.BASE_HARNESS_CONFIG_DIR] : []),
  ])
})

export function fileInDirectory(dir: string, name: string) {
  return [path.join(dir, `${name}.json`), path.join(dir, `${name}.jsonc`)]
}
