import { LayerNode } from "@base-harness/core/effect/layer-node"
import { AppNodeBuilder } from "@base-harness/core/effect/app-node-builder"
import { Effect, Layer, Schema, Context } from "effect"
import { serviceUse } from "@base-harness/core/effect/service-use"
import { makeRuntime } from "@base-harness/core/effect/runtime"
import semver from "semver"
import { InstallationChannel, InstallationVersion } from "@base-harness/core/installation/version"
import { InstallationEvent } from "@base-harness/schema/installation-event"

export type Method = "curl" | "npm" | "yarn" | "pnpm" | "bun" | "brew" | "scoop" | "choco" | "unknown"
export type ReleaseType = "patch" | "minor" | "major"

export const Event = InstallationEvent

export function getReleaseType(current: string, latest: string): ReleaseType {
  const currMajor = semver.major(current)
  const currMinor = semver.minor(current)
  const newMajor = semver.major(latest)
  const newMinor = semver.minor(latest)
  if (newMajor > currMajor) return "major"
  if (newMinor > currMinor) return "minor"
  return "patch"
}

export const Info = Schema.Struct({
  version: Schema.String,
  latest: Schema.String,
}).annotate({ identifier: "InstallationInfo" })
export type Info = Schema.Schema.Type<typeof Info>

export function userAgent(client = "cli") {
  return `base-harness/${InstallationChannel}/${InstallationVersion}/${client}`
}

export const USER_AGENT = userAgent()

export function isPreview() {
  return InstallationChannel !== "latest"
}

export function isLocal() {
  return InstallationChannel === "local"
}

export class UpgradeFailedError extends Schema.TaggedErrorClass<UpgradeFailedError>()("UpgradeFailedError", {
  stderr: Schema.String,
}) {
  override get message() {
    return this.stderr
  }
}

export interface Interface {
  readonly info: () => Effect.Effect<Info>
  readonly method: () => Effect.Effect<Method>
  readonly latest: (method?: Method) => Effect.Effect<string>
  readonly upgrade: (method: Method, target: string) => Effect.Effect<void, UpgradeFailedError>
}

export class Service extends Context.Service<Service, Interface>()("@base-harness/Installation") {}
export const use = serviceUse(Service)

const unavailable = "Automatic updates are not available in the independent base-harness distribution."
const service = Service.of({
  info: () => Effect.succeed({ version: InstallationVersion, latest: InstallationVersion }),
  method: () => Effect.succeed("unknown" as Method),
  latest: () => Effect.succeed(InstallationVersion),
  upgrade: () => Effect.fail(new UpgradeFailedError({ stderr: unavailable })),
})
const layer = Layer.succeed(Service, service)

export const node = LayerNode.make({ service: Service, layer, deps: [] })

const { runPromise } = makeRuntime(Service, AppNodeBuilder.build(node))
export const latest = (...args: Parameters<Interface["latest"]>) => runPromise((s) => s.latest(...args))
export const method = () => runPromise((s) => s.method())
export const upgrade = (...args: Parameters<Interface["upgrade"]>) => runPromise((s) => s.upgrade(...args))

export * as Installation from "."
