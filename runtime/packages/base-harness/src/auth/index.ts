import { LayerNode } from "@base-harness/core/effect/layer-node"
import path from "path"
import { Effect, Layer, Record, Result, Schema, Context } from "effect"
import { NonNegativeInt } from "@base-harness/core/schema"
import { Global } from "@base-harness/core/global"
import { FSUtil } from "@base-harness/core/fs-util"
import { GlobalSecretRegistryHub } from "@base-harness/core/secret-registry"

export const OAUTH_DUMMY_KEY = "opencode-oauth-dummy-key"

const file = path.join(Global.Path.data, "auth.json")

const fail = (message: string) => (cause: unknown) => new AuthError({ message, cause })

export class Oauth extends Schema.Class<Oauth>("OAuth")({
  type: Schema.Literal("oauth"),
  refresh: Schema.String,
  access: Schema.String,
  expires: NonNegativeInt,
  accountId: Schema.optional(Schema.String),
  enterpriseUrl: Schema.optional(Schema.String),
}) {}

export class Api extends Schema.Class<Api>("ApiAuth")({
  type: Schema.Literal("api"),
  key: Schema.String,
  metadata: Schema.optional(Schema.Record(Schema.String, Schema.String)),
}) {}

export class WellKnown extends Schema.Class<WellKnown>("WellKnownAuth")({
  type: Schema.Literal("wellknown"),
  key: Schema.String,
  token: Schema.String,
}) {}

export const Info = Schema.Union([Oauth, Api, WellKnown]).annotate({ discriminator: "type", identifier: "Auth" })
export type Info = Schema.Schema.Type<typeof Info>

const register = (providerID: string, info: Info) => {
  if (info.type === "oauth") GlobalSecretRegistryHub.register([info.access, info.refresh], `auth:${providerID}`)
  if (info.type === "api") GlobalSecretRegistryHub.register(info.key, `auth:${providerID}`)
  if (info.type === "wellknown") GlobalSecretRegistryHub.register([info.key, info.token], `auth:${providerID}`)
}

export class AuthError extends Schema.TaggedErrorClass<AuthError>()("AuthError", {
  message: Schema.String,
  cause: Schema.optional(Schema.Defect()),
}) {}

export interface Interface {
  readonly get: (providerID: string) => Effect.Effect<Info | undefined, AuthError>
  readonly all: () => Effect.Effect<Record<string, Info>, AuthError>
  readonly set: (key: string, info: Info) => Effect.Effect<void, AuthError>
  readonly remove: (key: string) => Effect.Effect<void, AuthError>
}

export class Service extends Context.Service<Service, Interface>()("@base-harness/Auth") {}

const layer = Layer.effect(
  Service,
  Effect.gen(function* () {
    const fsys = yield* FSUtil.Service
    const decode = Schema.decodeUnknownOption(Info)

    const all = Effect.fn("Auth.all")(function* () {
      if (process.env.BASE_HARNESS_AUTH_CONTENT) {
        try {
          const result = JSON.parse(process.env.BASE_HARNESS_AUTH_CONTENT) as Record<string, Info>
          for (const [providerID, info] of Object.entries(result)) register(providerID, info)
          return result
        } catch (err) {}
      }

      // A missing store is normal before the first login. Avoid constructing a
      // read failure on this hot path; still tolerate removal between probe and read.
      const data = (yield* fsys.existsSafe(file).pipe(
        Effect.flatMap((exists) => exists ? fsys.readJson(file) : Effect.succeed({})),
        Effect.orElseSucceed(() => ({})),
      )) as Record<string, unknown>
      const result = Record.filterMap(data, (value) => Result.fromOption(decode(value), () => undefined))
      for (const [providerID, info] of Object.entries(result)) register(providerID, info)
      return result
    })

    const get = Effect.fn("Auth.get")(function* (providerID: string) {
      return (yield* all())[providerID]
    })

    const set = Effect.fn("Auth.set")(function* (key: string, info: Info) {
      register(key, info)
      const norm = key.replace(/\/+$/, "")
      const data = yield* all()
      if (norm !== key) delete data[key]
      delete data[norm + "/"]
      yield* fsys
        .writeJson(file, { ...data, [norm]: info }, 0o600)
        .pipe(Effect.mapError(fail("Failed to write auth data")))
    })

    const remove = Effect.fn("Auth.remove")(function* (key: string) {
      const norm = key.replace(/\/+$/, "")
      const data = yield* all()
      delete data[key]
      delete data[norm]
      yield* fsys.writeJson(file, data, 0o600).pipe(Effect.mapError(fail("Failed to write auth data")))
    })

    return Service.of({ get, all, set, remove })
  }),
)

export const node = LayerNode.make({ service: Service, layer: layer, deps: [FSUtil.node] })

export * as Auth from "."
