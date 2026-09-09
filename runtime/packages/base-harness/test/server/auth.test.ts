import { afterEach, describe, expect, test } from "bun:test"
import { ConfigProvider, Effect, Option, Redacted } from "effect"
import { ServerAuth as SharedServerAuth } from "@base-harness/server/auth"
import { Flag } from "@base-harness/core/flag/flag"
import { ServerAuth } from "../../src/server/auth"

const original = {
  BASE_HARNESS_SERVER_PASSWORD: Flag.BASE_HARNESS_SERVER_PASSWORD,
  BASE_HARNESS_SERVER_USERNAME: Flag.BASE_HARNESS_SERVER_USERNAME,
}

afterEach(() => {
  Flag.BASE_HARNESS_SERVER_PASSWORD = original.BASE_HARNESS_SERVER_PASSWORD
  Flag.BASE_HARNESS_SERVER_USERNAME = original.BASE_HARNESS_SERVER_USERNAME
})

describe("ServerAuth", () => {
  test("does not emit auth headers without a password", () => {
    Flag.BASE_HARNESS_SERVER_PASSWORD = undefined
    Flag.BASE_HARNESS_SERVER_USERNAME = "alice"

    expect(ServerAuth.header()).toBeUndefined()
    expect(ServerAuth.headers()).toBeUndefined()
  })

  test("defaults to the base-harness username", () => {
    Flag.BASE_HARNESS_SERVER_PASSWORD = "secret"
    Flag.BASE_HARNESS_SERVER_USERNAME = undefined

    expect(ServerAuth.headers()).toEqual({
      Authorization: `Basic ${Buffer.from("base-harness:secret").toString("base64")}`,
    })
  })

  test("shared server and Host use the same default credentials", async () => {
    Flag.BASE_HARNESS_SERVER_PASSWORD = "secret"
    Flag.BASE_HARNESS_SERVER_USERNAME = undefined
    const config = await Effect.runPromise(
      Effect.gen(function* () {
        return yield* SharedServerAuth.Config
      }).pipe(
        Effect.provide(SharedServerAuth.Config.layer),
        Effect.provide(ConfigProvider.layer(ConfigProvider.fromUnknown({ BASE_HARNESS_SERVER_PASSWORD: "secret" }))),
      ),
    )
    expect(config.username).toBe("base-harness")
    const previous = process.env.BASE_HARNESS_SERVER_USERNAME
    delete process.env.BASE_HARNESS_SERVER_USERNAME
    try {
      expect(SharedServerAuth.header({ password: "secret" })).toBe(ServerAuth.header())
    } finally {
      if (previous === undefined) delete process.env.BASE_HARNESS_SERVER_USERNAME
      else process.env.BASE_HARNESS_SERVER_USERNAME = previous
    }
    expect(SharedServerAuth.authorized({ username: "base-harness", password: Redacted.make("secret") }, config)).toBe(true)
    expect(SharedServerAuth.authorized({ username: "opencode", password: Redacted.make("secret") }, config)).toBe(false)
  })

  test("uses the configured username", () => {
    Flag.BASE_HARNESS_SERVER_PASSWORD = "secret"
    Flag.BASE_HARNESS_SERVER_USERNAME = "alice"

    expect(ServerAuth.headers()).toEqual({
      Authorization: `Basic ${Buffer.from("alice:secret").toString("base64")}`,
    })
  })

  test("prefers explicit credentials", () => {
    Flag.BASE_HARNESS_SERVER_PASSWORD = "secret"
    Flag.BASE_HARNESS_SERVER_USERNAME = "alice"

    expect(ServerAuth.headers({ password: "cli-secret", username: "bob" })).toEqual({
      Authorization: `Basic ${Buffer.from("bob:cli-secret").toString("base64")}`,
    })
  })

  test("validates decoded credentials against effect config", () => {
    const config = { password: Option.some("secret"), username: "alice" }

    expect(ServerAuth.required(config)).toBe(true)
    expect(ServerAuth.authorized({ username: "alice", password: Redacted.make("secret") }, config)).toBe(true)
    expect(ServerAuth.authorized({ username: "opencode", password: Redacted.make("secret") }, config)).toBe(false)
  })
})
